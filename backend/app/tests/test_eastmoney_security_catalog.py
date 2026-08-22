from app.data_sources.eastmoney_security_catalog import parse_security_catalog_payload


def test_security_catalog_fixture_only_keeps_supported_equity_listings() -> None:
    items = parse_security_catalog_payload(
        {
            "QuotationCodeTable": {
                "Data": [
                    {
                        "Code": "600519",
                        "Name": "贵州茅台",
                        "PinYin": "GZMT",
                        "JYS": "SH",
                        "Classify": "AStock",
                        "SecurityTypeName": "沪A",
                        "SecurityType": "1",
                        "TypeUS": "6",
                        "QuoteID": "1.600519",
                    },
                    {
                        "Code": "920185",
                        "Name": "贝特瑞",
                        "PinYin": "BTR",
                        "JYS": "BJ",
                        "Classify": "AStock",
                        "SecurityTypeName": "京A",
                        "SecurityType": "27",
                        "TypeUS": "80",
                        "QuoteID": "0.920185",
                    },
                    {
                        "Code": "09992",
                        "Name": "泡泡玛特",
                        "PinYin": "PPMT",
                        "JYS": "HK",
                        "Classify": "HK",
                        "SecurityTypeName": "港股",
                        "SecurityType": "6",
                        "TypeUS": "3",
                        "QuoteID": "116.09992",
                    },
                    {
                        "Code": "03032",
                        "Name": "恒生科技ETF",
                        "JYS": "HK",
                        "Classify": "HK",
                        "SecurityTypeName": "港股",
                        "SecurityType": "6",
                        "TypeUS": "1",
                        "QuoteID": "116.03032",
                    },
                    {
                        "Code": "89988",
                        "Name": "阿里巴巴-WR",
                        "JYS": "HK",
                        "Classify": "HK",
                        "SecurityTypeName": "港股",
                        "SecurityType": "6",
                        "TypeUS": "3",
                        "QuoteID": "116.89988",
                    },
                    {
                        "Code": "TME",
                        "Name": "腾讯音乐",
                        "PinYin": "TXYL",
                        "JYS": "NYSE",
                        "Classify": "UsStock",
                        "SecurityTypeName": "美股",
                        "SecurityType": "7",
                        "TypeUS": "3",
                        "QuoteID": "106.TME",
                    },
                    {
                        "Code": "BRK_A",
                        "Name": "伯克希尔哈撒韦-A",
                        "JYS": "NYSE",
                        "Classify": "UsStock",
                        "SecurityTypeName": "美股",
                        "SecurityType": "7",
                        "TypeUS": "10",
                        "QuoteID": "106.BRK_A",
                    },
                    {
                        "Code": "TMED",
                        "Name": "Tuttle Capital 2X Long TME Daily Target ETF",
                        "JYS": "NASDAQ",
                        "Classify": "UsStock",
                        "SecurityTypeName": "美股",
                        "SecurityType": "7",
                        "TypeUS": "5",
                        "QuoteID": "105.TMED",
                    },
                ]
            }
        }
    )

    assert [(item.ticker, item.security_type) for item in items] == [
        ("600519.SH", "common_stock"),
        ("920185.BJ", "common_stock"),
        ("09992.HK", "common_stock"),
        ("TME.US", "ads"),
        ("BRK_A.US", "common_stock"),
    ]
