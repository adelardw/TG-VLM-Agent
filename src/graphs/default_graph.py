from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
import numpy as np

from .structured_outputs import (MemoryFindStructuredOutputs, MemoryRecallStructuredOutputs,
                                 MemoryRememberStructuredOutputs, MemoryWonderStructuredOutputs,SummarizeStructuredOutputs)

from .prompts import (memory_find_prompt, recall_prompt, wonder_prompt,
                      rememeber_prompt, summarize_prompt,default_system_prompt)

from .graph_states import DefaultAssistant
from .utils import format_history_for_llm

from src.users_cache import thread_memory
from src.llm import OpenRouterChat, OpenRouterEmbeddings
from src.config import OPEN_ROUTER_API_KEY, TEXT_IMAGE_MODEL, EMBED_MODEL
from src.beautylogger import logger

ckpt = InMemorySaver()


llm = OpenRouterChat(OPEN_ROUTER_API_KEY, model_name=TEXT_IMAGE_MODEL)
embed = OpenRouterEmbeddings(OPEN_ROUTER_API_KEY, EMBED_MODEL)

wonder_assistant = wonder_prompt | llm.with_structured_output(MemoryWonderStructuredOutputs)
# rememeber_assistant = rememeber_prompt | llm.with_structured_output(MemoryRememberStructuredOutputs)
#find_assistant = memory_find_prompt | llm.with_structured_output(MemoryFindStructuredOutputs)
recall_assistant = recall_prompt | llm.with_structured_output(MemoryRecallStructuredOutputs)
summarize_assistant = summarize_prompt | llm.with_structured_output(SummarizeStructuredOutputs)
chat_assistant = default_system_prompt | llm | StrOutputParser()



async def router(state):
    logger.info('[ROUTER]')
    if state["make_history_summary"]:
        return "summarize"
    else:
        return "wonder"

async def summarize_node(state):
    logger.info('[SUMMARIZE]')
    user_id = state['user_id']
    thread_id = state['thread_id']
    previous_thread_id = state['previous_thread_id']
    history = thread_memory.get_thread_history(previous_thread_id)
    wonder_history = thread_memory.get_wonder_thread_moments(previous_thread_id)
    
    history = format_history_for_llm(history, wonder_history)
    
    summary_results = await summarize_assistant.ainvoke({'history': history})
    thread_memory.add_user_thread_summary(summary=summary_results.summary,
                                          theme=summary_results.theme,
                                          user_id=user_id,
                                          thread_id=previous_thread_id)
    
    return state


async def wonder_node(state):
    logger.info('[WONDER]')
    wonder_results = await wonder_assistant.ainvoke({"local_context": f"Локальная память: {state['local_context']}" ,
                                                     "user_message": f"Сообщение пользователя: {state['user_message']}"}) 
    
    if wonder_results.need_remember:
        thread_memory.add_wonder_to_history(state['thread_id'], user_message=state['user_message'],
                                            reason=wonder_results.reason)
    return state

async def recall_node(state):
    """Ищет похожие саммари в прошлом (Global Context)."""
    
    logger.info('[RECALL]')
    recall_results = await recall_assistant.ainvoke({
        "local_context": f"Локальная память: {state.get('local_context', [])}",
        "user_message": f"Сообщение пользователя: {state['user_message']}"
    }) 
    
    global_context_str = ""

    if recall_results.need_recall:
        summaries_data = thread_memory.get_all_user_summaries(state['user_id'])
        
        if summaries_data:
            full_summaries = [s['summary'] for s in summaries_data if s.get('summary')]
            
            if full_summaries:
                
                summary_embeddings = np.array(await embed.aembed_documents(full_summaries))
                
                query_embedding = np.array(await embed.aembed_query(state['user_message']))
                scores = summary_embeddings @ query_embedding
                top_k = 3
                if len(scores) < top_k:
                    top_k = len(scores)
                
                ind = np.argsort(scores)[-top_k:][::-1]
                found_texts = [f"- {full_summaries[i]}" for i in ind]
                global_context_str = "\n".join(found_texts)

    state['global_context'] = global_context_str
    return state


async def answer_node(state):
    logger.info('[ANSWER]')
    response = await chat_assistant.ainvoke({
        'global_context': f"Глобальный контекст (прошлые темы): {state.get('global_context', 'Нет данных')}",
        'local_context': f"Локальная память (текущий разговор): {state.get('local_context', [])}",
        "user_message": f"Сообщение пользователя: {state['user_message']}" 
    })
    
    state['generation'] = response
    return state
        
workflow = StateGraph(DefaultAssistant)

workflow.add_node("summarize", summarize_node)
workflow.add_node("wonder", wonder_node)
workflow.add_node("recall", recall_node)
workflow.add_node("answer", answer_node)


workflow.add_conditional_edges(
    START,
    router,
    {
        "summarize": "summarize",
        "wonder": "wonder"
    }
)

workflow.add_edge("summarize", "wonder") 
workflow.add_edge("wonder", "recall")
workflow.add_edge("recall", "answer")
workflow.add_edge("answer", END)


tgc_default = workflow.compile(checkpointer=InMemorySaver())