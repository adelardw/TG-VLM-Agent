from langgraph.graph import START, StateGraph, END
from graphs.prompts import make_full_news_prompt, make_search_query_prompt, news_summary_agent_prompt
from graphs.graph_states import NewsGraphState
from graphs.structured_outputs import NewsStructuredOutputs, SearchStructuredOutputs
from langchain_core.output_parsers import StrOutputParser
from langchain.text_splitter import RecursiveCharacterTextSplitter
import asyncio
import numpy as np
from graphs.utils import search

from llm import OpenRouterChat, OpenRouterEmbeddings
from config import OPEN_ROUTER_API_KEY, EMBED_MODEL

llm = OpenRouterChat(api_key=OPEN_ROUTER_API_KEY)
embed = OpenRouterEmbeddings(OPEN_ROUTER_API_KEY, EMBED_MODEL)
splitter = RecursiveCharacterTextSplitter(chunk_size = 1000, chunk_overlap = 100)

search_agent = make_search_query_prompt | llm.with_structured_output(SearchStructuredOutputs)
#news_summary_agent = news_summary_agent_prompt | llm.with_structured_output(NewsStructuredOutputs)
final_news_agent = make_full_news_prompt | llm | StrOutputParser()


async def search_node(state):
    search_query = (await search_agent.ainvoke({"input": state['input']})).search_query
    search_results = await asyncio.to_thread(search, search_query)
    
    state['search_query'] = search_query
    state['original_news'] = search_results

    return state


async def summary_node(state):

    if state['original_news']:
        docs = splitter.create_documents(state['original_news'])
        texts_to_embed = [d.page_content for d in docs]
        embeddings = np.array(await embed.aembed_documents(texts_to_embed))
        query_embedding = np.array(await embed.aembed_query(state['input']))
        scores = embeddings @ query_embedding
        top_k = min(len(scores), 5)
        
        ind = np.argsort(scores)[-top_k:][::-1]
        found_texts = [f"- {docs[i].page_content}" for i in ind]

        state['batch_results'] = found_texts
    else:
        state['batch_results'] = ['']

    return state

async def make_news_node(state):
    if state['batch_results']:
        make_news_input = "Найденные ближайшие чанки" + ",".join([content for content in state['batch_results']])
        state['output'] = await final_news_agent.ainvoke({"news": make_news_input,
                                                          "input": state['input']})
    else:
        state['output'] = "Новости не найдены, видимо, сетевая проблема"
    return state


workflow = StateGraph(NewsGraphState)

workflow.add_node('Search', search_node)
workflow.add_node('Summarization', summary_node)
workflow.add_node('MakeNews', make_news_node)

workflow.add_edge(START, "Search")
workflow.add_edge("Search","Summarization")
workflow.add_edge("Summarization", "MakeNews")
workflow.add_edge('MakeNews', END)

graph = workflow.compile(debug=False)

#if __name__ =='__main__':
#    print(graph.invoke({'input': "Расскажи о последних новостях экономики в РФ"}))