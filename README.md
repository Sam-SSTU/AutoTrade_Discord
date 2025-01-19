# AutoTrade Discord

AI-powered trading bot that monitors and analyzes KOL messages from Discord and Telegram for automated trading.

## Project Structure

```
/AutoTrade_Discord
    /backend             # Python FastAPI backend
    /frontend           # Next.js frontend
```

## Prerequisites

- Python 3.9+
- Node.js 16+
- MongoDB
- Redis

## Setup Instructions

### Backend Setup

1. Create virtual environment:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
- Copy `.env.example` to `.env`
- Update the configuration values

4. Run the backend server:
```bash
uvicorn src.main:app --reload
```

### Frontend Setup

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Run the development server:
```bash
npm run dev
```

## Features

- Real-time message monitoring from Discord and Telegram
- AI-powered message analysis and trading signal detection
- Risk management and trading execution
- Web-based management interface
- Performance analytics and reporting

## License

MIT 