# Nature Finance RAG database and API for working with World Bank country and climate development reports (CCDRs)

## Getting Started

1. Clone the repository with `git clone https://github.com/Teal-Insights/nature-finance-rag-api && cd nature-finance-rag-api`
2. Copy `.env.example` to `.env` and fill in the values
3. Run `docker compose up` to start the Postgres database

## Synchronization with the client

This repository contains startup scripts for the RAG database and API. The database forms the data storage layer for the CCDR Explorer. See [the CCDR Explorer client repository](https://github.com/Teal-Insights/nature-finance-rag-client) for more information.