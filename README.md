# 🚀 Web3 Fast Chatbot

A high-performance, specialized chatbot focused exclusively on Web3, cryptocurrency, and blockchain technology. Built with FastAPI, featuring real-time price data, intelligent intent detection, and streaming responses.

![Web3 Chatbot](https://img.shields.io/badge/Web3-Chatbot-blue?style=for-the-badge&logo=ethereum)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=for-the-badge&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)

## ✨ Features

### **Specialized Web3 Focus**
- **Cryptocurrency Prices**: Real-time price data for Bitcoin, Ethereum, and 20+ major cryptocurrencies
- **Blockchain Education**: Detailed explanations of DeFi, NFTs, smart contracts, and Web3 concepts
- **Strict Scope**: Exclusively handles Web3/crypto topics, politely declines off-topic queries

### **High Performance**
- **Streaming Responses**: Real-time response generation for better UX
- **Redis Caching**: 30-second price caching, 1-hour conversation context caching
- **Intent Detection**: Smart routing to optimize response times
- **Async Architecture**: Built on FastAPI with full async support


## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Backend** | FastAPI + Python 3.11 | High-performance async API |
| **LLM** | Groq (Llama 4 Scout) | Fast, efficient language model |
| **Caching** | Redis | Response and price data caching |
| **Price Data** | CoinGecko API | Real-time cryptocurrency prices |
| **Frontend** | HTML5 + Vanilla JS | Lightweight, responsive UI |
| **Deployment** | Docker + Docker Compose | Containerized deployment |

### Environment Variables

```bash
# API Configuration
GROQ_API_KEY=your_groq_api_key_here
COINGECKO_API_KEY=your_coingecko_api_key_here  # Optional

# Cache Settings
CACHE_PRICE_TTL=30           # Price cache duration (seconds)
CACHE_CHAT_TTL=3600          # Chat cache duration (seconds)

# Application Settings
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=true
```

## 🐳 Docker Deployment

### Development
```bash
# Start with Redis
docker-compose up --build

# Access the application
open http://localhost:8000
```

## 💬 Usage Examples

### Cryptocurrency Prices
```
User: "What's the current price of Ethereum?"
Bot: "💰 ETH Price Update
      Current Price: $2,456.78
      24h Change: +3.45% 📈
      Market Cap: $295,234,567,890
      Updated: 14:30:25 (live)"
```

### Web3 Education
```
User: "What is DeFi?"
Bot: "DeFi (Decentralized Finance) refers to financial services 
      built on blockchain technology that operate without 
      traditional intermediaries like banks..."
```

### Intent Detection
The chatbot automatically detects query types:
- **price_query**: "BTC price", "How much is Solana?"
- **web3_chat**: "Explain smart contracts", "What are NFTs?"
- **wallet_query**: "Check my balance" (coming soon)
- **non_web3**: Politely declined with redirect to Web3 topics


## Development

### Project Structure
```
web3-fast-chatbot/
├── main.py                 # FastAPI application
├── config.py              # Configuration management
├── intent_detector.py     # Query classification
├── services/
│   ├── chat_service.py    # LLM chat handling
│   └── price_service.py   # Cryptocurrency prices
├── utils/
│   ├── cache.py           # Redis cache manager
│   ├── groq_client.py     # Groq API client
│   └── coingecko_client.py # CoinGecko API client
├── static/
│   ├── index.html         # Frontend interface
│   └── script.js          # Frontend logic
└── docker-compose.yml     # Docker configuration
```


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Groq** for providing fast LLM inference
- **CoinGecko** for comprehensive cryptocurrency data
- **FastAPI** for the excellent async framework
- **Redis** for reliable caching infrastructure
