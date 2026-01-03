from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from datetime import datetime, timedelta
from deprecated import deprecated 
from langchain.text_splitter import RecursiveCharacterTextSplitter
import asyncio

from time import perf_counter
import numpy as np
from graphs.utils import search

from .structured_outputs import (AnswerSchema,RecallAction,SearchStructuredOutputs,SelectedThreads,
                                 FactExtractionSchema,SummarizeStructuredOutputs,SearchQuerySchema)

from .prompts import (recall_prompt,query_prompt,make_search_query_prompt, memory_selector_prompt,
                    summarize_prompt,default_system_prompt, fact_extraction_prompt)

from .graph_states import DefaultAssistant
from .utils import prepare_cache_messages_to_langchain

from src.users_cache import thread_memory, embed
from src.llm import OpenRouterChat
from src.config import OPEN_ROUTER_API_KEY, TEXT_IMAGE_MODEL
from src.beautylogger import logger

ckpt = InMemorySaver()


llm = OpenRouterChat(OPEN_ROUTER_API_KEY, model_name=TEXT_IMAGE_MODEL)
splitter = RecursiveCharacterTextSplitter(chunk_size = 1000, chunk_overlap = 100)


recall_analyzer = recall_prompt | llm.with_structured_output(RecallAction)
summarize_assistant = summarize_prompt | llm.with_structured_output(SummarizeStructuredOutputs)
chat_assistant = default_system_prompt | llm.with_structured_output(AnswerSchema)
generate_query_assistant = query_prompt | llm.with_structured_output(SearchQuerySchema)
extractor_chain = fact_extraction_prompt | llm.with_structured_output(FactExtractionSchema)
search_agent = make_search_query_prompt | llm.with_structured_output(SearchStructuredOutputs)
memory_selector = memory_selector_prompt | llm.with_structured_output(SelectedThreads)


async def find_similar_mem_chunks(documents: list[str], query: str, top_k: int = 3):
    if not documents:
        return [], []
    
    summary_embeddings = np.array(await embed.aembed_documents(documents))
    query_embedding = np.array(await embed.aembed_query(query))
    
    scores = summary_embeddings @ query_embedding
    
    top_indices = np.argsort(scores)[-top_k:][::-1]
    
    results = []
    for idx in top_indices:
        results.append((idx, scores[idx]))
        
    return results

async def router(state):
    logger.info('[ROUTER]')
    logger.info(f'[USER QUERY] {state["user_message"]}')
    if state.get("make_history_summary"):
        return "summarize"
    
    local_ctx = state.get('local_context', [])
    if len(local_ctx) >= thread_memory.context_local_window:
        return "local_summarize"
        
    return "recall"


async def local_summarize_node(state):
    logger.info('[LOCAL SUMMARIZE - ROLLING WINDOW]')
    thread_id, user_id = state['thread_id'], state['user_id']
    
    current_window_history = thread_memory.get_local_history(thread_id)
    history_lc = prepare_cache_messages_to_langchain(current_window_history)
    
    summary_results = await summarize_assistant.ainvoke({'history': history_lc})
    
    captured_images = []
    for msg in current_window_history:
        if (meta := msg.get('metadata')) and (imgs := meta.get('images')):
            captured_images.extend(imgs if isinstance(imgs, list) else [imgs])
    
    captured_images = list(dict.fromkeys(captured_images))

    thread_memory.clear_thread_local_history(thread_id)
    summary_content = f"Контекст беседы: {summary_results.summary}"
    thread_memory._add_msg_local_history(thread_id, 'assistant', summary_content, 
                                         metadata={'time': state['time'].isoformat(),
                                                   'images': captured_images})
    
    await thread_memory.add_user_thread_summary(
        summary=summary_results.summary,
        user_id=user_id, 
        thread_id=thread_id,
        metadata={"time": state['time'].isoformat()}
    )
    
    state['local_context'] = thread_memory.get_local_history(thread_id)
    logger.info(f'[LOCAL CTX] {state.get("local_context", [])}')
    return state


async def summarize_node(state):
    logger.info('[SUMMARIZE]')
    user_id = state['user_id']
    previous_thread_id = state['previous_thread_id']
    
    history = thread_memory.get_thread_history(previous_thread_id)
    history_lc = prepare_cache_messages_to_langchain(history)
    
    captured_images = []
    for msg in history:
        if (meta := msg.get('metadata')) and (imgs := meta.get('images')):
            captured_images.extend(imgs if isinstance(imgs, list) else [imgs])
    
    captured_images = list(dict.fromkeys(captured_images))
    
    
    start = perf_counter()
    summary_results = await summarize_assistant.ainvoke({'history': history_lc})
    end = perf_counter() - start
    state['time'] = state['time'] + timedelta(seconds=int(end))
    
    await thread_memory.add_user_thread_summary(
        summary=summary_results.summary,
        user_id=user_id,
        thread_id=previous_thread_id,
        metadata={"time": (state['time']).isoformat(),
                  'images': captured_images} 
    )

    logger.info(f'[LOCAL CTX] {state.get("local_context", [])}')
    return state


async def web_search_node(state):
    logger.info('[WEB SEARCH]')
    search_results = await asyncio.to_thread(search, state['web_query'] or state['user_message'])
    if not search_results:
        return state

    docs = splitter.create_documents(search_results)
    texts = [d.page_content for d in docs]
    
    embeddings = np.array(await embed.aembed_documents(texts))
    query_vec = np.array(await embed.aembed_query(state['web_query']))
    scores = embeddings @ query_vec
    
    top_indices = np.argsort(scores)[-3:][::-1]
    web_context = "\n".join([f"Источник [Интернет]: {texts[i]}" for i in top_indices])
    
    return {"web_context": web_context}


async def recall_node(state):

    logger.info('[RECALL ANALYZER]')
    action = await recall_analyzer.ainvoke({
        "history": prepare_cache_messages_to_langchain(state['local_context']),
        "user_message": state['user_message']
    })
    
    return {
        "need_recall": action.need_recall,
        "need_web_search": action.need_web_search,
        "search_query": action.search_query,
        "web_query": action.web_query
    }


async def memory_node(state):

    logger.info('[MEMORY FETCH]')
    user_id = state['user_id']
    summaries = thread_memory.get_all_summaries_for_search(user_id)
    if not summaries:
        return {"global_context": []}
    
    query_vec = np.array(await embed.aembed_query(state['search_query']))
    q_user = np.array(await embed.aembed_query(state['user_message']))
    
    results = []
    raws = []
    for s in summaries:
        score_query = np.dot(query_vec, np.array(s['vector']))
        score_user = np.dot(q_user, np.array(s['vector']))
        score = max(score_query, score_user)
        logger.info(f"score: [{score}] | summary: [{s['summary']}]")
        if score > 0.45:
            results.append(s)
            
    if not results:
        logger.info("[MEMORY] No vector matches found above threshold.")
        return {"global_context": []}

    formatted_summaries = ""
    for s in results:
        formatted_summaries += f"ID: {s['thread_id']} | Суть: {s['summary']}\n"

    selection = await memory_selector.ainvoke({
            "user_message": state['user_message'],
            "summaries_list": formatted_summaries})

    raws = []
    if selection.relevant_thread_ids:
        logger.info(f"[LLM MEMORY SELECTED] {selection.relevant_thread_ids}")
        
        for t_id in selection.relevant_thread_ids:
            summary_item = next((s for s in summaries if s['thread_id'] == t_id), None)
            if not summary_item: 
                continue
            
            raw_history = thread_memory.get_thread_history(t_id)
            
            raws.append({"role": "system", "content": f"--- ПАМЯТЬ: ТРЕД {t_id} ---"})
            raws.append({"role": "assistant", "content": f"Краткая суть: {summary_item['summary']}"})
            raws.extend(raw_history[-7:])

    return {"global_context": raws}
        

def route_after_recall(state):
    targets = []
    if state.get("need_recall"):
        targets.append("memory_fetch")
    if state.get("need_web_search"):
        targets.append("web_search")
    
    return targets if targets else ["answer"]


async def answer_node(state):
    logger.info('[ANSWER - WITH CoT]')
    
    
    web_info = state.get('web_context', '') 
    web_data = []
    if web_info:
        web_data = [{"role": "system", "content": f"АКТУАЛЬНЫЕ ДАННЫЕ ИЗ ИНТЕРНЕТА:\n{web_info}"}]
        logger.info(f'[WEB CTX] {web_data}')

    history_lc = prepare_cache_messages_to_langchain(state.get('global_context', []),
                                                     local=False)

    web_lc = prepare_cache_messages_to_langchain(web_data, local=False)
    locals_lc = prepare_cache_messages_to_langchain(state['local_context'])
    full_history_lc = history_lc + web_lc + locals_lc 

    all_images = []
    if state.get('image_url'):
        all_images.append(state['image_url'])

    input_dict = {
        'history': full_history_lc, 
        "user_message": f"Время отправки сообщения: [{state['time'].isoformat()}]."\
                        f"Сообщение от пользователя: {state['user_message']}",
    }
    
    if all_images:
        input_dict["image_url"] = all_images 
        
    response = await chat_assistant.ainvoke(input_dict)
    state['generation'] = response
    state['global_context'] = []
    state['web_context'] = ''
    return state
        
workflow = StateGraph(DefaultAssistant)

workflow.add_node("summarize", summarize_node)
workflow.add_node("recall", recall_node)
workflow.add_node("memory_fetch", memory_node)
workflow.add_node("web_search", web_search_node)
workflow.add_node("answer", answer_node)
workflow.add_node("local_summarize", local_summarize_node)

workflow.add_conditional_edges(
    START,
    router,
    {
        "summarize": "summarize",
        "local_summarize": "local_summarize",
        "recall": "recall"
    }
)

workflow.add_edge("local_summarize", "recall")

workflow.add_conditional_edges(
    "recall", 
    route_after_recall, 
    {
        "memory_fetch": "memory_fetch", 
        "web_search": "web_search", 
        "answer": "answer"
    }
)

workflow.add_edge("memory_fetch", "answer")
workflow.add_edge("web_search", "answer")

workflow.add_edge("summarize", "recall")
workflow.add_edge("answer", END)


tgc_default = workflow.compile(checkpointer=InMemorySaver())