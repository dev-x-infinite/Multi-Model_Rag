"""
agent.py
The "brain" -- decides whether to search the user's documents or answer
directly, using Groq's free-tier tool-calling. Every call is scoped to
one user_id so it never sees another user's documents.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

from groq import Groq
from vector_store import VectorStoreManager

client = Groq(api_key=os.environ["GROQ_API_KEY"])
store = VectorStoreManager()

MODEL = "llama-3.3-70b-versatile"

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "Search the user's uploaded documents (PDFs, images) for "
                "relevant information. Use this when the question could be "
                "about the user's specific files -- not for general "
                "knowledge questions you already know the answer to."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, rephrased for semantic search"
                    }
                },
                "required": ["query"]
            }
        }
    }
]


def ask(user_question: str, user_id: str) -> str:
    # Defined inside ask() so it closes over this specific request's
    # user_id -- the model can never accidentally search another user's
    # documents, because this function literally can't reach them.
    def search_documents(query: str) -> str:
        results = store.search(query, user_id=user_id, k=3)
        if not results:
            return "No relevant documents found for this user."
        return "\n\n".join(
            f"[Source: {r['source']}] (distance={r['distance']:.2f})\n{r['content']}"
            for r in results
        )

    available_tools = {"search_documents": search_documents}

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant with access to the user's "
                "uploaded documents via search_documents. Only search when "
                "the question seems related to their files. Cite the source "
                "when you use document content in your answer."
            )
        },
        {"role": "user", "content": user_question}
    ]

    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
        )

        message = response.choices[0].message

        assistant_msg = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in message.tool_calls
            ]
        messages.append(assistant_msg)

        if not message.tool_calls:
            return message.content or "I wasn't able to generate an answer for that."

        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            function_to_call = available_tools[function_name]
            result = function_to_call(**function_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })


if __name__ == "__main__":
    test_user = input("Enter a user_id for this test session: ")
    while True:
        question = input("\nAsk something (Ctrl+C to quit): ")
        answer = ask(question, test_user)
        print(f"\n{answer}")