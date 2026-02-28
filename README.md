# ai-helper-telegram

## Tech Stack
- MongoDB,
- PydanticAI
- GeminiAPI
- RAG
- AgentLightning loop
- Aiogram

## About ai-helper

This is Honda dealership's AI assistant to answer customers problems, check free mechanic slots to book a service,
agent's db right is read-only. He can compare different cars in stock, different types of detailing works.

He will never give a customer price of service (always depends on situation, complexity of work etc), he will never
He will never give a customer recommendations to fix something by himself

Run on telegram

# DB

This is simple example of database - mechanic slots, booked by whom, customer, also collection of car parts and prices
DB is seeded randomly by script


# Agent lightning loop

Runs every day on bad rated chats, teaching an agent new dialogues based on failed ones (marked finger down on telegram)


# Data

project/data/info.md is extended information about car dealership service for AI agent. This is information that he should know
on 10/10