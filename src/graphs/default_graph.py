from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from datetime import datetime, timedelta
from time import perf_counter
import numpy as np

from .structured_outputs import (AnswerSchema,RecallAction,
                                 FactExtractionSchema,SummarizeStructuredOutputs,SearchQuerySchema)

from .prompts import (recall_prompt,query_prompt,
                    summarize_prompt,default_system_prompt, fact_extraction_prompt)

from .graph_states import DefaultAssistant
from .utils import prepare_cache_messages_to_langchain

from src.users_cache import thread_memory, embed
from src.llm import OpenRouterChat
from src.config import OPEN_ROUTER_API_KEY, TEXT_IMAGE_MODEL
from src.beautylogger import logger

ckpt = InMemorySaver()


llm = OpenRouterChat(OPEN_ROUTER_API_KEY, model_name=TEXT_IMAGE_MODEL)

recall_analyzer = recall_prompt | llm.with_structured_output(RecallAction)
summarize_assistant = summarize_prompt | llm.with_structured_output(SummarizeStructuredOutputs)
chat_assistant = default_system_prompt | llm.with_structured_output(AnswerSchema)
generate_query_assistant = query_prompt | llm.with_structured_output(SearchQuerySchema)

extractor_chain = fact_extraction_prompt | llm.with_structured_output(FactExtractionSchema)


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
    return state


async def summarize_node(state):
    logger.info('[SUMMARIZE]')
    user_id = state['user_id']
    previous_thread_id = state['previous_thread_id']
    
    history = thread_memory.get_thread_history(previous_thread_id)
    history_lc = prepare_cache_messages_to_langchain(history)
    
    start = perf_counter()
    summary_results = await summarize_assistant.ainvoke({'history': history_lc})
    end = perf_counter() - start
    state['time'] = state['time'] + timedelta(seconds=int(end))
    
    await thread_memory.add_user_thread_summary(
        summary=summary_results.summary,
        theme=summary_results.theme,
        user_id=user_id,
        thread_id=previous_thread_id,
        metadata={"time": (state['time']).isoformat()} 
    )
    
    return state





async def recall_node(state):
    logger.info('[RECALL - OPTIMIZED]')
    user_id, query = state['user_id'], state['user_message']
    
    action = await recall_analyzer.ainvoke({
        "history": prepare_cache_messages_to_langchain(state['local_context']),
        "user_message": query
    })

    if not action.need_recall:
        return state

    summaries = thread_memory.get_all_summaries_for_search(user_id)
    if not summaries:
        return state

    query_vec = np.array(await embed.aembed_query(action.search_query))
    
    results = []
    for s in summaries:
        score = np.dot(query_vec, np.array(s['vector']))
        if score > 0.75:
            results.append(s)

    if results:
        best_match = sorted(results, key=lambda x: np.dot(query_vec, x['vector']), reverse=True)[0]
        raw_history = thread_memory.get_thread_history(best_match['thread_id'])
        
        state['global_context'] = [
            {"role": "system", "content": f"Вспомнил из темы '{best_match.get('theme')}': {best_match['summary']}"},
            *raw_history[-10:] 
        ]
        
        state['recalled_images'] = [
            img for msg in raw_history 
            if (imgs := msg.get('metadata', {}).get('images')) for img in (imgs if isinstance(imgs, list) else [imgs])
        ][:2]

    return state


async def answer_node(state):
    logger.info('[ANSWER - WITH CoT]')
    
    history_lc = prepare_cache_messages_to_langchain(state.get('global_context', []))
    locals_lc = prepare_cache_messages_to_langchain(state['local_context'])
    
    full_history_lc = history_lc + locals_lc

    all_images = []
    if state.get('recalled_images'):
        all_images.extend(state['recalled_images'])
    if state.get('image_url'):
        all_images.append(state['image_url'])

    input_dict = {
        'history': full_history_lc, 
        "user_message": f"Новое сообщение: {state['user_message']}",
        "datetime": f"Текущее время: {state['time']}" 
    }
    
    if all_images:
        input_dict["image_url"] = all_images 
        
    response = await chat_assistant.ainvoke(input_dict)
    state['generation'] = response
    
    return state
        
workflow = StateGraph(DefaultAssistant)

workflow.add_node("summarize", summarize_node)
workflow.add_node("recall", recall_node)
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
workflow.add_edge("summarize", "recall")
workflow.add_edge("recall", "answer")
workflow.add_edge("answer", END)


tgc_default = workflow.compile(checkpointer=InMemorySaver())