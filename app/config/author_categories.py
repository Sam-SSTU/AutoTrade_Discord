# 频道ID到博主分类的映射
CHANNEL_CATEGORIES = {
    # Anson的频道
    "1004719239250317322": "Anson",  # anson-trade-api
    "1004719460558569542": "Anson",  # ansonの交易
    "1004719494511460362": "Anson",  # jacksonの交易
    "1004719655459500083": "Anson",  # vip交易分析
    "1047878449844469760": "Anson",  # mingxuan的交易
    "1064876916642959432": "Anson",  # 67の养猪交易
    "1127599514895781979": "Anson",  # 鲨鱼の分享

    # VIVI的频道
    "1113105418663776316": "VIVI",  # btc每日更新
    "1113106196510035998": "VIVI",  # 短线交易策略
    "1165811530370134026": "VIVI",  # 每周交易策略
    "1165811567422615654": "VIVI",  # 现货交易策略
    "1179304542345642024": "VIVI",  # eth每日更新
    "1181833180458795028": "VIVI",  # 美股和etf
    "1222054267070709830": "VIVI",  # 日内交易策略
    "1222056574164533309": "VIVI",  # 牛市投资组合
    "1222059273534705704": "VIVI",  # 土狗-meme
    "1222067120775499776": "VIVI",  # 月度波段策略
    "1224751976877916221": "VIVI",  # 交易追踪

    # Illusion的频道
    "1192863230444445767": "Illusion",  # 现货交易
    "1192863450779631666": "Illusion",  # illusion行情分析
    "1192863520291815555": "Illusion",  # btc-eth合约
    "1222074740697464914": "Illusion",  # 1k-10k现货挑战
    "1222075460146434100": "Illusion",  # 土狗推荐
    "1309350078489825352": "Illusion",  # 1sol-1000sol挑战

    # 其他博主频道可以继续添加...
}

# 获取频道的博主分类
def get_author_category(channel_id: str) -> str:
    return CHANNEL_CATEGORIES.get(channel_id, "未分类") 