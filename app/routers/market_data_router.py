from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import Ativo
from app.schemas.api_schemas import (
    CotacaoOut,
    HistoricoItem,
    MacroDataOut,
    TickerSearchResult,
)
from app.services.market_data import (
    get_crypto_history,
    get_crypto_price,
    get_macro_data,
    get_stock_history,
    get_stock_price,
    is_crypto,
    to_crypto_id,
)

# Tickers B3 comuns para autocomplete rápido (sem bater no Yahoo)
_B3_TICKERS: dict[str, str] = {
    # --- Blue Chips / Ibovespa Top ---
    "PETR4": "Petrobras PN", "PETR3": "Petrobras ON",
    "VALE3": "Vale ON", "ITUB4": "Itaú Unibanco PN",
    "ITUB3": "Itaú Unibanco ON", "BBDC4": "Bradesco PN",
    "BBDC3": "Bradesco ON", "BBAS3": "Banco do Brasil ON",
    "ABEV3": "Ambev ON", "WEGE3": "WEG ON",
    "RENT3": "Localiza ON", "SUZB3": "Suzano ON",
    "JBSS3": "JBS ON", "GGBR4": "Gerdau PN",
    "RDOR3": "Rede D'Or ON", "EQTL3": "Equatorial ON",
    "BPAC11": "BTG Pactual Units", "PRIO3": "PRIO ON",
    "RADL3": "Raia Drogasil ON", "RAIL3": "Rumo ON",
    "LREN3": "Lojas Renner ON", "BBSE3": "BB Seguridade ON",
    "HAPV3": "Hapvida ON", "CSAN3": "Cosan ON",
    "KLBN11": "Klabin Units", "VIVT3": "Telefônica Brasil ON",
    "TOTS3": "TOTVS ON", "CMIG4": "Cemig PN",
    "ENEV3": "Eneva ON", "ELET3": "Eletrobras ON",
    "ELET6": "Eletrobras PNB", "SBSP3": "Sabesp ON",
    "MGLU3": "Magazine Luiza ON", "CPLE6": "Copel PNB",
    "TAEE11": "Taesa Units", "UGPA3": "Ultrapar ON",
    "CSNA3": "CSN ON", "GOAU4": "Metalúrgica Gerdau PN",
    "TIMS3": "TIM ON", "SANB11": "Santander Brasil Units",
    "AZUL4": "Azul PN", "EMBR3": "Embraer ON",
    "CPFE3": "CPFL Energia ON", "CMIN3": "CSN Mineração ON",
    "CRFB3": "Carrefour Brasil ON", "MULT3": "Multiplan ON",
    "IGTI11": "Iguatemi Units", "MRFG3": "Marfrig ON",
    "BEEF3": "Minerva ON", "BRFS3": "BRF ON",
    "YDUQ3": "Yduqs ON", "COGN3": "Cogna ON",
    "VBBR3": "Vibra Energia ON",
    # --- Bancos e Financeiras ---
    "ITSA4": "Itaúsa PN", "ITSA3": "Itaúsa ON",
    "B3SA3": "B3 ON", "CIEL3": "Cielo ON",
    "IRBR3": "IRB Brasil ON", "SULA11": "SulAmérica Units",
    "PSSA3": "Porto Seguro ON", "BRSR6": "Banrisul PNB",
    "ABCB4": "ABC Brasil PN", "BMGB4": "BMG PN",
    "BPAN4": "Banco Pan PN", "MODL11": "Banco Modal Units",
    # --- Energia e Utilities ---
    "ENBR3": "EDP Energias do Brasil ON", "NEOE3": "Neoenergia ON",
    "AURE3": "Auren Energia ON", "AESB3": "AES Brasil ON",
    "CMIG3": "Cemig ON", "CPLE3": "Copel ON",
    "EGIE3": "Engie Brasil ON", "TRPL4": "Transmissão Paulista PN",
    "ALUP11": "Alupar Units",
    "CSMG3": "Copasa ON", "SAPR11": "Sanepar Units",
    "SAPR4": "Sanepar PN", "GEPA4": "Gera Paranapanema PN",
    "OMGE3": "Omega Energia ON",
    # --- Varejo e Consumo ---
    "VIIA3": "Via ON", "AMER3": "Americanas ON",
    "PETZ3": "Petz ON", "SOMA3": "Grupo Soma ON",
    "ARZZ3": "Arezzo ON", "GRND3": "Grendene ON",
    "VULC3": "Vulcabras ON", "GUAR3": "Guararapes ON",
    "LJQQ3": "Quero-Quero ON", "AMAR3": "Marisa ON",
    "CEAB3": "C&A Brasil ON", "BHIA3": "Casas Bahia ON",
    "ASAI3": "Assaí ON", "PCAR3": "GPA ON",
    "MDIA3": "M.Dias Branco ON", "NTCO3": "Natura ON",
    "SMFT3": "Smart Fit ON",
    # --- Saúde ---
    "FLRY3": "Fleury ON", "DASA3": "Dasa ON",
    "QUAL3": "Qualicorp ON", "HYPE3": "Hypera ON",
    "ONCO3": "Oncoclínicas ON", "MATD3": "Mater Dei ON",
    "BLAU3": "Blau Farmacêutica ON",
    # --- Construção e Imobiliário ---
    "CYRE3": "Cyrela ON", "MRVE3": "MRV ON",
    "EZTC3": "EZTEC ON", "EVEN3": "Even ON",
    "DIRR3": "Direcional ON", "TRIS3": "Trisul ON",
    "TEND3": "Tenda ON", "LAVV3": "Lavvi ON",
    "PLPL3": "Plano & Plano ON", "MDNE3": "Moura Dubeux ON",
    "ALSO3": "Allos ON", "LOGG3": "LOG CP ON",
    "BRML3": "BR Malls ON", "HBSA3": "Hidrovias do Brasil ON",
    # --- Tecnologia e Telecom ---
    "LWSA3": "Locaweb ON", "CASH3": "Méliuz ON",
    "MLAS3": "Multilaser ON", "POSI3": "Positivo ON",
    "INTB3": "Intelbras ON", "NGRD3": "Neogrid ON",
    "BMOB3": "Bemobi ON", "SQIA3": "Sinqia ON",
    "DESK3": "Desktop ON",
    # --- Indústria e Materiais ---
    "USIM5": "Usiminas PNA", "FESA4": "Ferbasa PN",
    "CBAV3": "CBA ON", "UNIP6": "Unipar PNB",
    "BRKM5": "Braskem PNA", "KEPL3": "Kepler Weber ON",
    "TUPY3": "Tupy ON", "RAIZ4": "Raízen PN",
    "SMTO3": "São Martinho ON", "SLCE3": "SLC Agrícola ON",
    "AGRO3": "BrasilAgro ON", "TTEN3": "3Tentos ON",
    "CAML3": "Camil ON",
    # --- Transporte e Logística ---
    "CCRO3": "CCR ON", "ECOR3": "EcoRodovias ON",
    "GOLL4": "GOL PN", "STBP3": "Santos Brasil ON",
    "LOGN3": "Log-In ON",
    "MOVI3": "Movida ON", "VAMO3": "Vamos ON",
    # --- Seguros e Previdência ---
    "CXSE3": "Caixa Seguridade ON", "WIZC3": "Wiz ON",
    # --- Papel e Celulose ---
    "KLBN4": "Klabin PN", "KLBN3": "Klabin ON",
    "RANI3": "Irani ON", "DXCO3": "Dexco ON",
    # --- Siderurgia e Mineração ---
    "GGBR3": "Gerdau ON", "GOAU3": "Metalúrgica Gerdau ON",
    "USIM3": "Usiminas ON",
    # --- Petróleo e Gás ---
    "CGAS5": "Comgás PNA", "RECV3": "PetroRecôncavo ON",
    "RRRP3": "3R Petroleum ON",
    # --- Educação ---
    "ANIM3": "Ânima ON", "SEER3": "Ser Educacional ON",
    "VTRU3": "Vitru ON",
    # --- Outros ---
    "SEQL3": "Sequoia ON", "SIMH3": "Simpar ON",
    "PTBL3": "Portobello ON", "MYPK3": "Iochpe-Maxion ON",
    "TASA4": "Taurus PN", "FRAS3": "Fras-Le ON",
    "RSUL4": "Randon PN", "RAPT4": "Randon Part PN",
    "PGMN3": "Pague Menos ON", "ARML3": "Armac ON",
    "SBFG3": "Grupo SBF ON", "TFCO4": "Track & Field PN",
    "ALPA4": "Alpargatas PN", "CVCB3": "CVC ON",
    "MBLY3": "Mobly ON",
}

_CRYPTO_TICKERS: dict[str, str] = {
    # --- Top 20 por Market Cap ---
    "bitcoin": "Bitcoin (BTC)", "ethereum": "Ethereum (ETH)",
    "tether": "Tether (USDT)", "binancecoin": "BNB (BNB)",
    "solana": "Solana (SOL)", "ripple": "XRP (Ripple)",
    "usd-coin": "USD Coin (USDC)", "cardano": "Cardano (ADA)",
    "dogecoin": "Dogecoin (DOGE)", "tron": "TRON (TRX)",
    "avalanche-2": "Avalanche (AVAX)", "chainlink": "Chainlink (LINK)",
    "polkadot": "Polkadot (DOT)", "polygon": "Polygon (MATIC)",
    "litecoin": "Litecoin (LTC)", "shiba-inu": "Shiba Inu (SHIB)",
    "dai": "Dai (DAI)", "uniswap": "Uniswap (UNI)",
    "stellar": "Stellar (XLM)", "cosmos": "Cosmos (ATOM)",
    # --- Layer 1 / Layer 2 ---
    "near": "NEAR Protocol (NEAR)", "arbitrum": "Arbitrum (ARB)",
    "optimism": "Optimism (OP)", "aptos": "Aptos (APT)",
    "sui": "Sui (SUI)", "sei-network": "Sei (SEI)",
    "fantom": "Fantom (FTM)", "algorand": "Algorand (ALGO)",
    "hedera-hashgraph": "Hedera (HBAR)", "internet-computer": "Internet Computer (ICP)",
    "kaspa": "Kaspa (KAS)", "mantle": "Mantle (MNT)",
    "stacks": "Stacks (STX)", "injective-protocol": "Injective (INJ)",
    "celestia": "Celestia (TIA)", "ton": "Toncoin (TON)",
    "base": "Base (BASE)",
    # --- DeFi ---
    "aave": "Aave (AAVE)", "maker": "Maker (MKR)",
    "lido-dao": "Lido DAO (LDO)", "the-graph": "The Graph (GRT)",
    "compound-governance-token": "Compound (COMP)",
    "curve-dao-token": "Curve DAO (CRV)",
    "pancakeswap-token": "PancakeSwap (CAKE)",
    "1inch": "1inch (1INCH)", "sushi": "SushiSwap (SUSHI)",
    "jupiter": "Jupiter (JUP)", "raydium": "Raydium (RAY)",
    "pendle": "Pendle (PENDLE)", "ondo-finance": "Ondo (ONDO)",
    # --- Gaming / Metaverso ---
    "the-sandbox": "The Sandbox (SAND)", "decentraland": "Decentraland (MANA)",
    "axie-infinity": "Axie Infinity (AXS)", "gala": "Gala (GALA)",
    "immutable-x": "Immutable X (IMX)", "enjincoin": "Enjin Coin (ENJ)",
    "illuvium": "Illuvium (ILV)", "render-token": "Render (RNDR)",
    # --- IA / Infraestrutura ---
    "fetch-ai": "Fetch.ai (FET)", "singularitynet": "SingularityNET (AGIX)",
    "ocean-protocol": "Ocean Protocol (OCEAN)", "bittensor": "Bittensor (TAO)",
    "worldcoin-wld": "Worldcoin (WLD)", "akash-network": "Akash (AKT)",
    "filecoin": "Filecoin (FIL)", "arweave": "Arweave (AR)",
    "theta-token": "Theta (THETA)",
    # --- Meme Coins ---
    "pepe": "Pepe (PEPE)", "floki": "Floki (FLOKI)",
    "bonk": "Bonk (BONK)", "dogwifcoin": "dogwifhat (WIF)",
    "brett": "Brett (BRETT)", "mog-coin": "Mog Coin (MOG)",
    # --- Stablecoins e Outros ---
    "first-digital-usd": "FDUSD (FDUSD)", "true-usd": "TrueUSD (TUSD)",
    "frax": "Frax (FRAX)",
    "wrapped-bitcoin": "Wrapped Bitcoin (WBTC)",
    "lido-staked-ether": "Lido Staked ETH (stETH)",
    "rocket-pool-eth": "Rocket Pool ETH (rETH)",
    # --- Privacy ---
    "monero": "Monero (XMR)", "zcash": "Zcash (ZEC)",
    # --- Exchanges / CEX tokens ---
    "crypto-com-chain": "Cronos (CRO)", "okb": "OKB (OKB)",
    "kucoin-shares": "KuCoin Token (KCS)",
    "leo-token": "LEO Token (LEO)",
    # --- Oracles / Data ---
    "band-protocol": "Band Protocol (BAND)", "api3": "API3 (API3)",
    "pyth-network": "Pyth Network (PYTH)",
    # --- Cross-chain ---
    "thorchain": "THORChain (RUNE)", "wormhole": "Wormhole (W)",
    "layerzero": "LayerZero (ZRO)",
    "quant-network": "Quant (QNT)", "vechain": "VeChain (VET)",
}

router = APIRouter(prefix="/market", tags=["Dados de Mercado"])


@router.get("/cotacao/{ticker}", response_model=CotacaoOut)
def cotacao(ticker: str, db: Session = Depends(get_db)):
    if is_crypto(ticker):
        data = get_crypto_price(to_crypto_id(ticker), db)
    else:
        data = get_stock_price(ticker.upper(), db)
    if not data:
        raise HTTPException(status_code=404, detail=f"Não foi possível obter cotação para {ticker}")
    return data


@router.get("/historico/{ticker}", response_model=list[HistoricoItem])
def historico(
    ticker: str,
    periodo: str = Query("1y", pattern="^(1mo|3mo|6mo|1y|2y|5y|max)$"),
    db: Session = Depends(get_db),
):
    if is_crypto(ticker):
        data = get_crypto_history(to_crypto_id(ticker), periodo, db)
    else:
        data = get_stock_history(ticker.upper(), periodo, db)
    if not data:
        raise HTTPException(status_code=404, detail=f"Não foi possível obter histórico para {ticker}")
    return data


@router.get("/search", response_model=list[TickerSearchResult])
def buscar(
    q: str = Query(..., min_length=1),
    tipo: str | None = Query(None, pattern="^(acao|crypto)$"),
    db: Session = Depends(get_db),
):
    """Busca rápida de tickers: DB local + lista estática. Sem scraping."""
    query = q.strip().upper()
    seen: set[str] = set()
    results: list[dict] = []

    # 1. Ativos já cadastrados no portfolio (instantâneo)
    db_ativos = db.query(Ativo).filter(
        Ativo.ticker.ilike(f"%{q}%") | Ativo.nome.ilike(f"%{q}%")
    ).limit(10).all()
    for a in db_ativos:
        key = a.ticker.lower()
        if key not in seen:
            seen.add(key)
            results.append({"ticker": a.ticker, "nome": a.nome or a.ticker, "origem": "portfolio"})

    # 2. Lista estática B3
    if tipo != "crypto":
        for ticker, nome in _B3_TICKERS.items():
            if len(results) >= 15:
                break
            if ticker.lower() not in seen and (query in ticker or query in nome.upper()):
                seen.add(ticker.lower())
                results.append({"ticker": ticker, "nome": nome, "origem": "b3"})

    # 3. Lista estática Crypto
    if tipo != "acao":
        q_lower = q.strip().lower()
        for crypto_id, nome in _CRYPTO_TICKERS.items():
            if len(results) >= 15:
                break
            if crypto_id not in seen and (q_lower in crypto_id or q_lower in nome.lower()):
                seen.add(crypto_id)
                results.append({"ticker": crypto_id, "nome": nome, "origem": "crypto"})

    return results


@router.get("/macro", response_model=MacroDataOut)
def macro(db: Session = Depends(get_db)):
    return get_macro_data(db)
