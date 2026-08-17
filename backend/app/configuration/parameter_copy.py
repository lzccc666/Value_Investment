# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterCopy:
    label: str
    description: str


DATA_SAMPLING_COPY = {
    "company_list_limit": ParameterCopy(
        "公司列表每页默认数量",
        "004 公司搜索未指定每页数量时返回的公司数；调大后每页公司更多、请求和渲染量也更大，调小后分页更频繁。",
    ),
    "company_list_limit_max": ParameterCopy(
        "公司列表单次请求上限",
        "004 公司列表接口允许请求的最大公司数；只限制单次请求规模，不改变公司池总数，也不进入分析或估值。",
    ),
    "financial_display_periods": ParameterCopy(
        "财务页面默认报告期数",
        "005 财务页和财务证据包默认读取的最近报告期数；一个报告期可包含多张报表，调大可看到更长历史但会增加读取量。",
    ),
    "analysis_financial_periods": ParameterCopy(
        "单个分析师读取财务期数",
        "创建 008 分析时写入该分析师快照的最近财务期数；调大提供更长财务历史，调小会减少趋势依据，不改变已经生成的分析。",
    ),
    "valuation_financial_records": ParameterCopy(
        "估值读取财务记录上限",
        "创建 010 估值草稿时读取的财务底稿记录数上限；这里按记录计数而非报告期，同期利润表、现金流量表和资产负债表会分别计数。",
    ),
    "announcement_lookback_years": ParameterCopy(
        "公告同步回溯年数",
        "006 同步公告的起始时间为当前时间向前减去该年数；调大能抓取更早公告，但仍受公告保留数量和最大翻页数限制。",
    ),
    "announcement_retention_limit": ParameterCopy(
        "每家公司公告保留上限",
        "006 每家公司同步后最多保留的最新公告数；超过上限会按发布时间淘汰更早公告，并影响后续 008 可选公告范围。",
    ),
    "announcement_page_size": ParameterCopy(
        "公告来源每页请求数量",
        "向东方财富公告接口每次请求的记录数；调大通常减少请求页数，调小会增加翻页次数，不直接改变最终保留上限。",
    ),
    "announcement_max_pages": ParameterCopy(
        "公告抓取最大翻页数",
        "单次公告同步允许访问的最大页数；达到上限仍未结束时同步会报错，防止异常分页无限占用网络资源。",
    ),
    "analysis_announcement_pool": ParameterCopy(
        "分析师公告初选池大小",
        "008 在排序前最多读取的最新公告数；排序后仍只采用“分析师最终采用公告数”，因此调大主要扩大候选范围。",
    ),
    "analysis_announcement_items": ParameterCopy(
        "单个分析师最终采用公告数",
        "008 按公告类别、会计主题、关键词和摘要完整度排序后，写入单个分析师快照的公告数量上限。",
    ),
    "analysis_evidence_items": ParameterCopy(
        "单个分析师最终采用外部证据数",
        "008 按可信度和重要性加权排序后，写入单个分析师快照的 007 外部证据数量上限。",
    ),
    "external_evidence_limit": ParameterCopy(
        "单次搜索最终入库证据上限",
        "007 一次外部搜索最多创建的 Evidence 数；调大可保留更多合格证据，但不会把被过滤的价格敏感内容或未验证线索变成正式证据。",
    ),
    "external_search_default_results": ParameterCopy(
        "每条搜索查询默认候选数",
        "007 未指定候选数量时，每条搜索查询向搜索提供方请求的结果数；它控制模型筛选前的候选量，不等于最终入库数量。",
    ),
    "announcement_model_chars": ParameterCopy(
        "单篇公告深度摘要输入上限",
        "006 深度摘要送入模型的公告正文字符上限；超长正文按“头部占比”保留开头，其余额度保留结尾。",
    ),
    "announcement_keyword_summary_chars": ParameterCopy(
        "公告快速摘要截取长度",
        "006 快速摘要从公告文本中保留的字符数；只影响关键词式快速摘要的可见上下文，不控制深度摘要。",
    ),
    "announcement_head_ratio": ParameterCopy(
        "超长公告头部保留比例",
        "公告正文超过深度摘要输入上限时，头部字符数 = 输入上限 × 本比例，其余字符额度从正文结尾截取；调高更重视开头，调低保留更多结尾。",
    ),
    "analysis_excerpt_chars": ParameterCopy(
        "分析快照单段文字上限",
        "008 压缩公司、公告、证据和财务说明时每段文字的字符上限；调小可能丢失上下文，调大增加模型输入，但不增加条目数量。",
    ),
    "manual_import_model_chars": ParameterCopy(
        "手工导入送模型正文上限",
        "007 手工导入文本送给证据提取模型的字符上限；超出部分不参与模型抽取，因此可能影响最终结构化事实。",
    ),
    "manual_import_snapshot_chars": ParameterCopy(
        "手工导入审计快照正文上限",
        "007 在运行快照中保存的手工导入正文字符上限；用于事后追溯模型依据，不改变送给模型的输入上限。",
    ),
    "evidence_excerpt_chars": ParameterCopy(
        "网页正文证据摘录上限",
        "007 从搜索结果网页读取并送入证据模型的正文字符上限；调大可保留更多网页上下文，也会增加读取和模型输入量。",
    ),
    "search_snippet_chars": ParameterCopy(
        "搜索结果快照摘要上限",
        "007 在搜索运行快照中保存的单条摘要字符上限；只影响审计快照长度，不改变网页正文摘录和模型判断。",
    ),
    "search_title_chars": ParameterCopy(
        "搜索结果快照标题上限",
        "007 在搜索运行快照中保存的单条标题字符上限；超长标题会被截断，只影响审计展示。",
    ),
    "memo_list_items": ParameterCopy(
        "备忘录模型风险与缺口条目上限",
        "009 向综合模型提供关键风险、反方证据和数据缺口时各类列表的条目上限；调大提供更多叙事上下文，不产生数值评分。",
    ),
    "price_decision_history_limit": ParameterCopy(
        "价格决策历史默认条数",
        "011 历史列表未指定数量时返回的最近价格决策条数；只影响列表读取，不改变价格状态和建议买入价公式。",
    ),
}


FINANCIAL_FLAG_COPY = {
    "stability_periods": ParameterCopy(
        "财务稳定性观察期数",
        "判断财务序列是否稳定时最多使用的最近连续期数；有至少 3 个有效值即可判断，调大可把更多历史纳入最大值与最小值比较。",
    ),
    "stability_range": ParameterCopy(
        "财务稳定性最大振幅",
        "稳定条件为观察期内“最大值 - 最小值”不超过该百分点；调高更容易判为稳定，调低更严格。",
    ),
    "trend_change": ParameterCopy(
        "相邻财务趋势显著变化幅度",
        "按 (本期 - 上期) / |上期| 计算；高于该值标记上升，低于其相反数标记下降，区间内视为基本稳定。",
    ),
    "revenue_yoy_min": ParameterCopy(
        "收入同比增长预警下限",
        "最新收入同比增长低于该值时触发“收入增长偏弱”预警；调高会更早预警，调低会容忍更大的收入下降。",
    ),
    "net_profit_yoy_min": ParameterCopy(
        "净利润同比增长预警下限",
        "最新归母净利润同比增长低于该值时触发“利润增长偏弱”预警；调高更严格。",
    ),
    "profit_revenue_gap_min": ParameterCopy(
        "利润增速落后收入的预警差值",
        "计算“净利润同比增速 - 收入同比增速”；结果低于该值时提示利润增长明显落后于收入，数值越接近 0 越严格。",
    ),
    "asset_liability_ratio_max": ParameterCopy(
        "资产负债率预警上限",
        "资产负债率高于该值时触发高负债风险；调低会让更多公司触发预警，并可能通过财务旗标提高 010 初始折现率。",
    ),
    "ocf_to_revenue_min": ParameterCopy(
        "经营现金流占收入预警下限",
        "经营现金流净额 / 营业收入低于该值时提示收入现金含量偏弱；调高对现金回收质量要求更高。",
    ),
    "fcf_to_profit_min": ParameterCopy(
        "自由现金流占净利润预警下限",
        "自由现金流 / 归母净利润低于该值时提示利润缺少自由现金流支撑；自由现金流 = 经营现金流 - 资本开支。",
    ),
    "investment_profit_ratio_abs_max": ParameterCopy(
        "投资收益占净利润绝对值上限",
        "|投资收益 / 归母净利润| 超过该值时提示利润可持续性风险；使用绝对值，因此大额投资损失也会触发。",
    ),
    "fair_value_profit_ratio_abs_max": ParameterCopy(
        "公允价值变动占净利润绝对值上限",
        "|公允价值变动损益 / 归母净利润| 超过该值时提示利润受估值变动影响较大；调低更严格。",
    ),
    "impairment_profit_ratio_max": ParameterCopy(
        "减值损失占净利润上限",
        "减值损失 / 归母净利润超过该值时提示资产质量风险；调低会更早标记减值压力。",
    ),
    "non_operating_profit_ratio_abs_max": ParameterCopy(
        "营业外收支占净利润绝对值上限",
        "|营业外收支净额 / 归母净利润| 超过该值时提示非经常性利润占比较高。",
    ),
    "effective_tax_rate_min": ParameterCopy(
        "有效税率正常区间下限",
        "有效税率 = 所得税费用 / 利润总额；低于该值时提示税率口径异常，需要复核一次性税收影响。",
    ),
    "effective_tax_rate_max": ParameterCopy(
        "有效税率正常区间上限",
        "有效税率 = 所得税费用 / 利润总额；高于该值时提示税率异常，需复核递延税项或一次性费用。",
    ),
    "deducted_profit_ratio_min": ParameterCopy(
        "扣非净利润占归母净利润下限",
        "扣非归母净利润 / 归母净利润低于该值时提示非经常性收益贡献较大；调高会提高主营利润纯度要求。",
    ),
    "margin_decline": ParameterCopy(
        "利润率单期下降预警幅度",
        "本期毛利率、营业利润率或净利率较上期下降超过该百分点时触发对应预警；调小更敏感。",
    ),
    "period_expense_rise": ParameterCopy(
        "期间费用率单期上升预警幅度",
        "本期期间费用率较上期上升超过该百分点时提示费用纪律恶化；期间费用率按期间费用合计 / 营业收入计算。",
    ),
    "finance_expense_rise": ParameterCopy(
        "财务费用率单期上升预警幅度",
        "本期财务费用 / 营业收入较上期上升超过该百分点时提示融资成本或杠杆压力。",
    ),
}


ANALYST_NAMES = {
    "buffett": "巴菲特",
    "peter_lynch": "彼得·林奇",
    "munger": "芒格",
    "duan_yongping": "段永平",
    "graham": "格雷厄姆",
    "fisher": "费雪",
    "lin_yuan": "林园",
    "li_lu": "李录",
}

DIMENSION_NAMES = {
    "business_quality": "商业质量",
    "moat_durability": "护城河持久性",
    "cash_flow_reliability": "现金流可靠性",
    "management_quality": "管理质量",
    "pricing_power": "定价权",
    "growth_runway": "增长空间",
    "demand_durability": "需求持续性",
    "execution_quality": "执行质量",
    "capital_intensity": "资本密集度",
    "balance_sheet_risk": "资产负债表风险",
    "permanent_loss_risk": "永久损失风险",
    "cyclicality": "周期性",
    "accounting_quality": "会计质量",
}

STATUS_NAMES = {
    "pass": "通过",
    "neutral": "中性",
    "unknown": "未知",
    "warn": "谨慎",
    "fail": "未通过",
}
SCENARIO_NAMES = {"conservative": "保守", "base": "中性", "optimistic": "乐观"}


def parameter_copy(path: tuple[str, ...], config: dict[str, object]) -> ParameterCopy:
    dotted = ".".join(path)
    domain = path[0]

    if domain == "data_sampling" and len(path) == 2:
        return DATA_SAMPLING_COPY[path[1]]

    if domain == "financial_flags":
        if path[1] == "cagr_years":
            horizon = "短期" if path[2] == "0" else "长期"
            return ParameterCopy(
                f"{horizon}复合增长率计算年限",
                f"计算收入、净利润和自由现金流的{horizon} CAGR：若有 n 年完整数据，则使用 (期末值 / 期初值)^(1/n) - 1；年限越长越平滑。",
            )
        return FINANCIAL_FLAG_COPY[path[1]]

    if domain == "analyst_engine":
        return _analyst_engine_copy(path)

    if domain == "valuation_rule_matrix":
        return _rule_matrix_copy(path, config)

    if domain == "memo_decision":
        return _memo_copy(path)

    if domain == "valuation_models":
        return _valuation_copy(path)

    if domain == "price_decision":
        return _price_copy(path)

    raise KeyError(f"未审计的参数文案：{dotted}")


def _analyst_engine_copy(path: tuple[str, ...]) -> ParameterCopy:
    group, leaf = path[1], path[-1]
    if group == "model_temperatures":
        contexts = {
            "announcement": ("公告深度摘要模型随机性", "006 单篇公告深度摘要"),
            "evidence_plan": ("外部证据搜索规划模型随机性", "007 搜索关键词和查询计划生成"),
            "evidence_extract": (
                "外部证据提取模型随机性",
                "007 网页证据及手工导入文本的结构化抽取",
            ),
            "analyst": ("分析师判断模型随机性", "008 单个分析师的规则判断与文字结论"),
            "memo": ("综合备忘录模型随机性", "009 综合投资备忘录文字生成"),
        }
        label, target = contexts[leaf]
        return ParameterCopy(
            label,
            f"控制{target}；越低越稳定、重复运行更一致，越高表达和判断波动更大，不改变确定性财务公式。",
        )
    if group == "base_profile_scores":
        analyst = ANALYST_NAMES[leaf]
        return ParameterCopy(
            f"{analyst}基础行业适配分",
            f"公司尚未叠加行业特征修正时，{analyst}视角的行业框架起始分；该分先截断到行业匹配上限，再与规则覆盖和证据支持加权。",
        )
    if group == "profile_default_score":
        return ParameterCopy(
            "未知分析师基础适配分结构兜底",
            "只有分析师标识未出现在八位内置分析师基础分中时才使用；当前有效配置要求八位基础分完整，因此正常 008 运行不会触发本值。",
        )
    if group == "feature_adjustments":
        entries = {
            "consumer_brand_primary": (
                "消费品牌对巴菲特、段永平和林园的适配加分",
                "公司文本命中消费或品牌特征时，加到巴菲特、段永平和林园的行业适配分",
            ),
            "consumer_brand_secondary": (
                "消费品牌对芒格、彼得·林奇和李录的适配加分",
                "公司文本命中消费或品牌特征时，加到芒格、彼得·林奇和李录的行业适配分",
            ),
            "tech_growth": (
                "科技成长对费雪和彼得·林奇的适配加分",
                "公司文本命中科技、研发或创新特征时，加到费雪和彼得·林奇的行业适配分",
            ),
            "cyclical_macro_defensive": (
                "周期行业对格雷厄姆和李录的适配加分",
                "公司命中周期或宏观敏感特征时，加到格雷厄姆和李录的行业适配分",
            ),
            "asset_heavy_graham": (
                "重资产行业对格雷厄姆的适配加分",
                "公司命中重资产、金融或地产特征时，加到格雷厄姆的行业适配分",
            ),
            "cash_flow_quality": (
                "存在经营现金流数据的质量视角加分",
                "财务快照存在经营现金流字段时，加到巴菲特、段永平和林园的行业适配分；它表示证据适配，不是现金流质量结论",
            ),
        }
        label, effect = entries[leaf]
        return ParameterCopy(
            label, f"{effect}；最终仍会与规则覆盖、证据支持及缺失惩罚共同计算视角适配度。"
        )
    if group == "profile_fit":
        entries = {
            "industry_weight": (
                "视角适配度中的行业匹配权重",
                "视角适配度 = 行业匹配分 × 本权重 + 规则主题覆盖率 × 对应权重 + 证据支持分 × 对应权重 - 不确定性扣分",
            ),
            "rule_coverage_weight": (
                "视角适配度中的规则主题覆盖权重",
                "视角适配度公式中“已覆盖核心主题数 / 该分析师核心主题总数”的权重",
            ),
            "evidence_support_weight": (
                "视角适配度中的证据支持权重",
                "视角适配度公式中证据支持分的权重；证据支持综合主题覆盖、财务数据、外部证据和已模型分析证据",
            ),
            "minimum": (
                "视角适配度最终下限",
                "完整视角适配度计算完成后使用的下限；结果再低也会抬高到该值",
            ),
            "maximum": (
                "视角适配度最终上限",
                "完整视角适配度计算完成后使用的上限；结果再高也会压低到该值",
            ),
            "industry_maximum": (
                "行业匹配分截断上限",
                "基础分析师分叠加行业特征修正后，进入综合公式前的行业匹配分上限；它不是最终适配度上限",
            ),
            "few_financial_periods": (
                "财务期数不足判定门槛",
                "可用财务期数少于该值时，视角适配度扣除“财务期数不足扣分”；等于该值时不扣",
            ),
            "few_financial_penalty": (
                "财务期数不足的适配度扣分",
                "财务期数低于门槛时，从视角适配度加权和中一次性扣除该值",
            ),
            "missing_external_penalty": (
                "缺少外部证据的适配度扣分",
                "没有任何 007 外部证据时，从视角适配度加权和中一次性扣除该值",
            ),
        }
        label, description = entries[leaf]
        return ParameterCopy(label, f"{description}；只影响新生成的 008 运行。")
    if group == "data_confidence":
        return _data_confidence_copy(leaf)
    if group == "announcement_ranking":
        entries = {
            "category_bonus": (
                "重点公告类别排序加分",
                "公告属于定期报告、业绩、分红、回购、治理或重大事项等重点类别时，一次性加入排序分",
            ),
            "accounting_bonus": (
                "会计主题公告排序加分",
                "公告文本命中审计、会计政策、减值、非经常性损益等会计主题时，一次性加入排序分",
            ),
            "term_bonus_each": (
                "每个分析师关键词排序加分",
                "公告每命中一个当前分析师关注关键词时加入该分值",
            ),
            "term_bonus_cap": (
                "分析师关键词排序加分上限",
                "关键词总加分 = min(本上限, 命中数 × 每词加分)，防止关键词数量压倒其他排序依据",
            ),
            "summary_bonus": (
                "已有公告摘要排序加分",
                "公告已经存在摘要时加入该值，使信息较完整的公告更容易进入最终采用列表",
            ),
        }
        label, description = entries[leaf]
        return ParameterCopy(
            label, f"{description}；排序分只决定 008 优先采用哪些公告，不直接表示看多或看空。"
        )
    if group == "evidence_ranking":
        subject = "可信度评分" if leaf == "credibility_weight" else "重要性评分"
        label = (
            "外部证据可信度排序权重" if leaf == "credibility_weight" else "外部证据重要性排序权重"
        )
        return ParameterCopy(
            label,
            f"外部证据排序分 = 可信度 × 对应权重 + 重要性 × 对应权重；本项控制{subject}的占比，两项权重必须合计 100%。",
        )
    if group == "source_priority":
        source_names = {
            "regulatory": "监管机构",
            "public_data": "政府或公共数据",
            "policy": "政策文件",
            "web": "普通网页",
            "company_news": "公司新闻",
            "industry_news": "行业新闻",
        }
        return ParameterCopy(
            f"{source_names[leaf]}来源优先分",
            f"008 选择外部证据时用于同类候选的来源质量加分；{source_names[leaf]}证据每条增加该分值，随后仍与可信度、重要性和发布时间共同排序。",
        )
    if group == "manual_import_credibility_cap":
        return ParameterCopy(
            "无来源链接手工证据可信度上限",
            "007 手工导入文本没有可复核来源链接时，最终可信度 = min(模型可信度, 本上限)；有链接时不应用此封顶。",
        )
    if group == "tier_thresholds":
        level = "高" if leaf == "high" else "中"
        boundary = (
            "达到该值标为高等级"
            if leaf == "high"
            else "低于高等级阈值但达到该值标为中等级，否则为低等级"
        )
        return ParameterCopy(
            f"分析师分数的{level}等级阈值",
            f"视角适配度和数据置信度共用该分级边界；{boundary}，只改变等级标签，不改变原始分数。",
        )
    raise KeyError(f"未审计的分析师参数：{'.'.join(path)}")


def _data_confidence_copy(leaf: str) -> ParameterCopy:
    entries = {
        "financial_weight": ("数据置信度中的财务覆盖权重", "最终数据置信度中财务覆盖子分的权重"),
        "announcement_weight": ("数据置信度中的公告覆盖权重", "最终数据置信度中公告覆盖子分的权重"),
        "external_weight": ("数据置信度中的外部证据权重", "最终数据置信度中外部证据质量子分的权重"),
        "source_balance_weight": (
            "数据置信度中的来源齐全度权重",
            "最终数据置信度中来源齐全度的权重；来源齐全度 = 财务、公告、外部证据三类中已存在的类别数 / 3",
        ),
        "minimum": ("数据置信度最终下限", "财务、公告、外部证据和会计事项综合计算后的最低允许分"),
        "maximum": ("数据置信度最终上限", "财务、公告、外部证据和会计事项综合计算后的最高允许分"),
        "accounting_event_penalty": (
            "存在会计口径事件的总分扣分",
            "检测到会计政策、审计或口径变化事件时，从最终数据置信度加权和中一次性扣除该值",
        ),
        "financial_present": ("存在财务数据的财务子分", "只要存在财务快照，就加入财务覆盖子分"),
        "financial_periods_bonus": (
            "财务期数达标的财务子分",
            "不同报告期数量达到设定门槛时，加入财务覆盖子分",
        ),
        "financial_periods_required": (
            "财务期数达标门槛",
            "可用财务报告期数量达到该值时获得“财务期数达标加分”",
        ),
        "latest_period_bonus": (
            "存在最新财务期的财务子分",
            "财务证据包能够识别最新报告期时加入财务覆盖子分",
        ),
        "profitability_bonus": (
            "盈利能力字段覆盖的财务子分",
            "来源覆盖矩阵包含盈利能力主题时加入财务覆盖子分",
        ),
        "cash_flow_bonus": (
            "现金流字段覆盖的财务子分",
            "来源覆盖矩阵包含现金流主题时加入财务覆盖子分",
        ),
        "financial_gap_penalty_each": (
            "每个财务数据缺口的子分扣分",
            "财务覆盖子分按“缺口数 × 本值”扣除",
        ),
        "financial_gap_penalty_cap": (
            "财务数据缺口总扣分上限",
            "财务覆盖子分的缺口扣分 = min(本上限, 缺口数 × 每缺口扣分)",
        ),
        "announcement_count_cap": (
            "公告数量覆盖最高子分",
            "公告数量子分 = min(本上限, 公告数 / 目标公告数 × 本上限)",
        ),
        "announcement_summary_cap": (
            "公告摘要覆盖最高子分",
            "公告摘要子分 = 已摘要公告数 / 公告总数 × 本上限",
        ),
        "announcement_target_count": (
            "公告数量满分目标",
            "公告数量达到该值时取得完整的公告数量覆盖子分；继续增加公告不会再提高该部分",
        ),
        "accounting_bonus": (
            "会计主题公告覆盖子分",
            "来源覆盖矩阵包含会计主题且存在公告时，加入公告覆盖子分",
        ),
        "governance_bonus": (
            "治理主题公告覆盖子分",
            "来源覆盖矩阵包含治理主题且存在公告时，加入公告覆盖子分",
        ),
        "external_present": (
            "存在外部证据的外部子分",
            "只要存在 007 外部证据，就加入外部证据质量子分",
        ),
        "external_analyzed_weight": (
            "已模型分析证据占比子分",
            "已模型分析证据数 / 外部证据总数 × 本值，加入外部证据质量子分",
        ),
        "external_source_bonus_each": (
            "每类外部来源的多样性子分",
            "每出现一种不同的外部证据来源类型，就加入该值",
        ),
        "external_source_bonus_cap": (
            "外部来源多样性子分上限",
            "来源多样性子分 = min(本上限, 来源类型数 × 每类加分)",
        ),
        "search_lead_penalty_each": (
            "每条未分析搜索线索的子分扣分",
            "每条 analysis_status=search_lead 的外部线索从外部证据质量子分中扣除该值",
        ),
        "search_lead_penalty_cap": (
            "未分析搜索线索总扣分上限",
            "搜索线索扣分 = min(本上限, 线索数 × 每条扣分)",
        ),
    }
    label, description = entries[leaf]
    return ParameterCopy(
        label, f"{description}；各子分先截断到 0%-100%，再按四项权重合成最终数据置信度。"
    )


def _rule_matrix_copy(path: tuple[str, ...], config: dict[str, object]) -> ParameterCopy:
    group, leaf = path[1], path[-1]
    if group == "status_scores":
        status = STATUS_NAMES[leaf]
        return ParameterCopy(
            f"010 规则“{status}”状态分",
            f"008 规则进入 010 时先把“{status}”换算为该分值；随后乘规则维度系数和分析师权重，五种状态都进入维度分母。",
        )
    if group == "safety_margin_additions":
        status = STATUS_NAMES[leaf]
        return ParameterCopy(
            f"010 “{status}”安全边际加点",
            "单条动态安全边际贡献 = 本加点 × 该分析师归一化权重 × 分析师数量缩放值；32 条贡献累加后截断到 0%-100%。",
        )
    entries = {
        "confidence_weight": (
            "010 分析师权重中的数据置信度占比",
            "分析师原始权重 = 数据置信度 × 本占比 + 视角适配度 × 对应占比",
        ),
        "profile_fit_weight": (
            "010 分析师权重中的视角适配度占比",
            "分析师原始权重 = 数据置信度 × 对应占比 + 视角适配度 × 本占比",
        ),
        "weight_exponent": (
            "010 分析师权重差异放大指数",
            "先把分析师原始权重除以全部分析师平均值，再取本指数次方并归一化；数值越大，高分分析师权重越集中",
        ),
        "analyst_score_min": (
            "进入 010 的分析师分数下限",
            "视角适配度和数据置信度进入权重公式前分别截断到该下限",
        ),
        "analyst_score_max": (
            "进入 010 的分析师分数上限",
            "视角适配度和数据置信度进入权重公式前分别截断到该上限",
        ),
        "dimension_score_min": (
            "010 单个估值维度分下限",
            "规则状态分 × 维度系数 × 分析师权重汇总并按绝对系数归一化后，低于该值的维度分被抬高到此下限",
        ),
        "dimension_score_max": (
            "010 单个估值维度分上限",
            "规则状态分 × 维度系数 × 分析师权重汇总并按绝对系数归一化后，高于该值的维度分被压低到此上限",
        ),
        "safety_margin_analyst_scale": (
            "动态安全边际分析师数量缩放值",
            "只用于单条安全边际贡献公式；默认 8 使每位分析师四条规则的贡献按八位完整委员会尺度累计，不进入估值维度和参数公式",
        ),
        "safety_margin_min": (
            "010 动态安全边际下限",
            "32 条逐项贡献累加后低于本值时抬高到本值，默认 0%",
        ),
        "safety_margin_max": (
            "010 动态安全边际上限",
            "32 条逐项贡献累加后高于本值时压低到本值；硬安全范围不得超过 100%",
        ),
    }
    if group != "rule_mappings":
        label, description = entries[group]
        return ParameterCopy(label, f"{description}；只影响新生成的 010 估值。")
    return _rule_mapping_copy(path, config)


def _rule_mapping_copy(path: tuple[str, ...], config: dict[str, object]) -> ParameterCopy:
    rule_key = path[2]
    mapping = config["valuation_rule_matrix"]["rule_mappings"][rule_key]
    profile_name = str(mapping.get("profile_name") or rule_key.split(".")[0])
    rule_label = str(mapping.get("rule_label") or rule_key.split(".")[-1])
    field = path[3]
    leaf = path[-1]
    if field == "dimensions":
        dimension = DIMENSION_NAMES.get(leaf, leaf)
        return ParameterCopy(
            f"{profile_name}《{rule_label}》到{dimension}的映射系数",
            f"贡献值 = 规则状态分 × 本系数 × {profile_name}权重，并计入“{dimension}”维度；正系数使通过状态提高维度分、不通过状态降低维度分。",
        )
    internal = {
        "profile_id": ("内部分析师标识", "规则矩阵的结构标识，不是可调计算参数。"),
        "profile_name": ("分析师中文名", "规则矩阵的展示文本，不是可调计算参数。"),
        "rule_id": ("内部规则标识", "32 条规则的稳定结构标识，不是可调计算参数。"),
        "rule_label": ("规则中文名", "规则矩阵的展示文本，不是可调计算参数。"),
        "calculation_role": ("规则计算角色", "32 条规则全部固定为 compute 并进入 010。"),
        "price_blind_compatible": ("无价格锚兼容标记", "确保 008-010 不读取当前价格的结构性标记。"),
    }
    label, description = internal[leaf]
    return ParameterCopy(f"{profile_name}《{rule_label}》{label}", description)


def _memo_copy(path: tuple[str, ...]) -> ParameterCopy:
    group, leaf = path[1], path[-1]
    if group == "min_successful_analysts":
        return ParameterCopy(
            "生成 009 所需最少成功分析师数",
            "最新成功的 008 分析师运行少于该数量时禁止生成综合备忘录，避免依据过少。",
        )
    if group == "model_confidence_map":
        level = {"low": "低", "medium": "中", "high": "高"}[leaf]
        return ParameterCopy(
            f"009 模型“{level}置信”写入分数",
            f"综合备忘录模型输出“{level}”置信等级时，AnalysisRun.confidence 保存为该数值；只做等级到数值的映射，不对 32 条规则打分。",
        )
    raise KeyError(f"未审计的备忘录参数：{'.'.join(path)}")


def _valuation_copy(path: tuple[str, ...]) -> ParameterCopy:
    group, leaf = path[1], path[-1]
    exact = {
        "forecast_years": (
            "现金流模型显式预测年数",
            "DCF、所有者收益、剩余收益和股息折现逐年预测的年数；调大延长显式预测期并推迟永续价值起点",
        ),
        "fcf_profit_cap": (
            "正常化自由现金流相对净利润上限",
            "当自由现金流可用时，正常化基准 FCF 不得超过净利润 × 本倍数，防止单年营运资金波动把现金流基数抬得过高",
        ),
        "fcf_profit_weak": (
            "自由现金流转化偏弱判定倍数",
            "正常化 FCF / 净利润低于该倍数时产生现金转化偏弱警告，并把该现金流基准的置信标记降为低；不会自动修改 DCF 模型权重",
        ),
        "default_growth": (
            "缺少可靠历史增长时的兜底增长率",
            "按优先级找不到可用的 FCF、净利润或收入 CAGR 时使用；随后仍会经过财务增长上下限和分析师调整",
        ),
        "financial_growth_min": (
            "历史财务增长率截断下限",
            "从增长来源优先级选出的历史 CAGR 低于该值时抬高到此下限，之后再叠加分析师维度调整",
        ),
        "financial_growth_max": (
            "历史财务增长率截断上限",
            "从增长来源优先级选出的历史 CAGR 高于该值时压低到此上限，防止异常高增长直接外推",
        ),
        "base_discount_rate": (
            "财务风险调整前的基础折现率",
            "初始折现率 = 本值 + min(折现率风险加点上限, 财务预警数 × 每预警加点 + 输入缺口数 × 每缺口加点)，随后截断到财务折现率上下限",
        ),
        "flag_discount_penalty": (
            "每个财务预警的折现率加点",
            "每个 005 财务预警把初始折现率提高该百分点；与输入缺口加点合计后受总加点上限约束",
        ),
        "gap_discount_penalty": (
            "每个估值输入缺口的折现率加点",
            "每个 010 输入缺口把初始折现率提高该百分点；与财务预警加点合计后受总加点上限约束",
        ),
        "discount_penalty_cap": (
            "财务预警和输入缺口的折现率总加点上限",
            "财务预警加点与输入缺口加点之和超过该值时按本值封顶",
        ),
        "financial_discount_min": (
            "财务阶段折现率下限",
            "基础折现率加风险点后、尚未加入分析师质量和风险调整前的最低折现率",
        ),
        "financial_discount_max": (
            "财务阶段折现率上限",
            "基础折现率加风险点后、尚未加入分析师质量和风险调整前的最高折现率",
        ),
        "base_terminal_growth": (
            "分析师调整前的基础永续增长率",
            "作为预测期结束后的长期增长起点，再叠加护城河、定价权和风险调整，并受永续增长边界及折现率差值约束",
        ),
        "discount_terminal_gap": (
            "折现率高于永续增长率的最小差值",
            "最终永续增长率不得高于折现率减去该百分点；避免终值公式分母接近 0 或变为负数",
        ),
        "analyst_impact_scale": (
            "分析师维度对估值假设的统一放大倍数",
            "质量分、成长分、风险分、分歧和未知比例乘各自参数调整系数后，再统一乘本倍数；0 表示关闭分析师对 G、OG、DR、TG、SP 的数值传导",
        ),
        "gap_penalty_cap": (
            "估值数据缺口风险分总上限",
            "高、中、低严重度缺口和证据包缺口按各自系数累加后，超过该值时封顶；该风险分进入综合风险分",
        ),
        "scenario_spread_base": (
            "三情景宽度起点",
            "情景宽度 SP = 本值 + 分析师影响倍数 × (风险分×风险系数 + 分歧×分歧系数 + 未知比例×未知系数)，再截断到上下限",
        ),
        "scenario_spread_min": (
            "三情景宽度下限",
            "计算得到的 SP 低于该值时抬高到此下限，防止保守、中性、乐观情景过度接近",
        ),
        "scenario_spread_max": (
            "三情景宽度上限",
            "计算得到的 SP 高于该值时压低到此上限，防止情景假设被拉得过宽",
        ),
        "permanent_loss_optimistic_cap": (
            "停止上调乐观永续增长的永久损失风险阈值",
            "永久损失风险负向分超过该阈值时，乐观情景永续增长率不得高于中性情景；该值是风险判定阈值，不是增长率上限",
        ),
        "model_weight_tolerance": (
            "五模型权重合计允许误差",
            "五个模型权重之和与 100% 的绝对差不得超过该值；仅用于浮点校验，不参与估值加权",
        ),
        "dispersion_ratio": (
            "估值模型中性结果分歧倍数阈值",
            "至少两个模型成功时，若最高中性估值 / 最低中性估值超过该倍数，则产生模型分歧警告并扣减估值置信度",
        ),
    }
    if group in exact:
        label, description = exact[group]
        return ParameterCopy(label, f"{description}；只影响新计算的 010 估值。")
    if group == "fcf_year_weights":
        index = int(path[2])
        labels = ["最近年度", "第二近年度", "第三近年度"]
        return ParameterCopy(
            f"正常化自由现金流的{labels[index]}权重",
            f"正常化 FCF 对{labels[index]}自由现金流使用的基准权重；缺少某年度时只对可用年度权重重新归一化。",
        )
    if group == "growth_source_priority":
        priority = int(path[2]) + 1
        condition = (
            "010 首先检查本项"
            if priority == 1
            else f"只有前 {priority - 1} 项都缺失或无效时，010 才检查本项"
        )
        return ParameterCopy(
            f"历史增长率来源第 {priority} 优先级",
            f"{condition}；一旦采用第 {priority} 项就不再混合更后面的增长来源。",
        )
    if group == "gap_penalties":
        names = {
            "high": "高严重度输入缺口",
            "medium": "中严重度输入缺口",
            "low": "低严重度输入缺口",
            "pack": "财务证据包整体缺口",
        }
        return ParameterCopy(
            f"{names[leaf]}风险分系数",
            f"每个{names[leaf]}按该值累加到数据缺口风险分，合计受“估值数据缺口风险分总上限”约束。",
        )
    if group == "composite_weights":
        score_group = path[2]
        dimension = path[3]
        group_name = {"quality": "质量综合分", "growth": "成长综合分", "risk": "风险综合分"}[
            score_group
        ]
        dim_name = DIMENSION_NAMES.get(dimension, "数据缺口风险")
        if dimension == "capital_intensity_penalty":
            description = "成长综合分会减去本权重 × 资本密集度负向分；调高会让重资产或高资本开支对成长判断的惩罚更强"
        elif score_group == "risk":
            description = f"{group_name}加入本权重 × {dim_name}负向分；调高会放大该风险来源对折现率和情景宽度的影响"
        else:
            description = (
                f"{group_name}加入本权重 × {dim_name}维度分；调高会放大该维度对后续估值假设的传导"
            )
        return ParameterCopy(f"{group_name}中的{dim_name}权重", f"{description}。")
    if group == "parameter_deltas":
        return _parameter_delta_copy(leaf)
    if group == "base_bounds":
        parameter = path[2]
        bound = "下限" if path[3] == "0" else "上限"
        names = {
            "growth": "中性现金流增长率",
            "owner_growth": "中性所有者收益增长率",
            "discount": "中性折现率",
            "terminal": "中性永续增长率",
        }
        return ParameterCopy(
            f"{names[parameter]}{bound}",
            f"财务起点叠加分析师调整后，{names[parameter]}超出范围时截断到该{bound}；之后再生成保守和乐观情景。",
        )
    if group == "scenarios":
        return _scenario_copy(path)
    if group == "model_weights":
        names = {
            "owner_earnings": "所有者收益模型",
            "dcf": "自由现金流折现模型",
            "residual_income": "剩余收益模型",
            "dividend_discount": "股息折现模型",
            "asset_value": "资产价值模型",
        }
        return ParameterCopy(
            f"{names[leaf]}基准权重",
            f"{names[leaf]}成功计算时在五模型综合估值中的基准占比；无法计算的模型会被剔除，其余可用模型按配置权重比例重新归一化。",
        )
    if group in {"non_cash_asset_haircuts", "equity_fallback_haircuts"}:
        scenario = SCENARIO_NAMES[leaf]
        if group == "non_cash_asset_haircuts":
            return ParameterCopy(
                f"资产价值模型{scenario}情景非现金资产保留比例",
                f"{scenario}情景资产价值 = 现金 + 非现金资产 × 本比例 - 总负债；比例越低，对存货、固定资产等非现金资产折扣越重。",
            )
        return ParameterCopy(
            f"资产价值模型{scenario}情景股东权益兜底比例",
            f"缺少总资产或总负债、但存在股东权益时，{scenario}情景资产价值 = 股东权益 × 本比例；只在资产负债数据不足的兜底路径使用。",
        )
    if group == "confidence":
        return _valuation_confidence_copy(leaf)
    if group == "sensitivity":
        if leaf == "growth_step":
            return ParameterCopy(
                "估值敏感性分析增长率步长",
                "敏感性矩阵分别使用中性现金流增长率减去本值、不变、加上本值，形成三行结果；不改变正式三情景估值。",
            )
        return ParameterCopy(
            "估值敏感性分析折现率步长",
            "敏感性矩阵分别使用中性折现率减去本值、不变、加上本值，形成三列结果；不改变正式三情景估值。",
        )
    raise KeyError(f"未审计的估值参数：{'.'.join(path)}")


def _parameter_delta_copy(leaf: str) -> ParameterCopy:
    entries = {
        "growth_growth": (
            "成长综合分对现金流增长率的调整系数",
            "现金流增长率调整量加入本系数 × 成长综合分",
        ),
        "growth_quality": (
            "质量综合分对现金流增长率的调整系数",
            "现金流增长率调整量加入本系数 × 质量综合分",
        ),
        "growth_risk": (
            "风险综合分对现金流增长率的调整系数",
            "现金流增长率调整量加入本系数 × 风险综合分；默认负值表示风险越高，增长率越低",
        ),
        "owner_growth_growth": (
            "成长综合分对所有者收益增长率的调整系数",
            "所有者收益增长率调整量加入本系数 × 成长综合分",
        ),
        "owner_growth_quality": (
            "质量综合分对所有者收益增长率的调整系数",
            "所有者收益增长率调整量加入本系数 × 质量综合分",
        ),
        "owner_growth_capital": (
            "资本密集度对所有者收益增长率的调整系数",
            "所有者收益增长率调整量加入本系数 × 资本密集度负向分；默认负值表示资本越密集，所有者收益增长越低",
        ),
        "owner_growth_risk": (
            "风险综合分对所有者收益增长率的调整系数",
            "所有者收益增长率调整量加入本系数 × 风险综合分；默认负值表示风险越高，增长率越低",
        ),
        "discount_quality": (
            "质量综合分对折现率的调整系数",
            "折现率调整量加入本系数 × 质量综合分；默认负值表示质量越高，要求回报率越低",
        ),
        "discount_risk": (
            "风险综合分对折现率的调整系数",
            "折现率调整量加入本系数 × 风险综合分；正值表示风险越高，折现率越高",
        ),
        "discount_disagreement": (
            "分析师维度分歧对折现率的调整系数",
            "折现率调整量加入本系数 × 13 个维度的平均分歧；正值表示分歧越大，折现率越高",
        ),
        "terminal_moat": (
            "护城河维度对永续增长率的调整系数",
            "永续增长率调整量加入本系数 × 护城河持久性维度分",
        ),
        "terminal_pricing": (
            "定价权维度对永续增长率的调整系数",
            "永续增长率调整量加入本系数 × 定价权维度分",
        ),
        "terminal_risk": (
            "风险综合分对永续增长率的调整系数",
            "永续增长率调整量加入本系数 × 风险综合分；默认负值表示风险越高，永续增长越低",
        ),
        "spread_risk": (
            "风险综合分对情景宽度的调整系数",
            "情景宽度加入本系数 × 风险综合分；正值表示风险越高，三情景距离越大",
        ),
        "spread_disagreement": (
            "分析师维度分歧对情景宽度的调整系数",
            "情景宽度加入本系数 × 13 个维度的平均分歧",
        ),
        "spread_unknown": (
            "未知计算规则比例对情景宽度的调整系数",
            "情景宽度加入本系数 × 未知 compute 规则数 / 全部 compute 规则数",
        ),
    }
    label, description = entries[leaf]
    return ParameterCopy(label, f"{description}；全部参数调整量最后统一乘“分析师影响放大倍数”。")


def _scenario_copy(path: tuple[str, ...]) -> ParameterCopy:
    scenario = path[2]
    field = path[3]
    scenario_name = SCENARIO_NAMES[scenario]
    parameter_names = {
        "growth": "现金流增长率",
        "owner_growth": "所有者收益增长率",
        "discount": "折现率",
        "terminal": "永续增长率",
    }
    if field.endswith("_spread"):
        parameter = field.removesuffix("_spread")
        return ParameterCopy(
            f"{scenario_name}情景{parameter_names[parameter]}的情景宽度倍数",
            f"{scenario_name}情景{parameter_names[parameter]} = 中性值 + 情景宽度 SP × 本倍数，再截断到该情景专属上下限；正值上调，负值下调。",
        )
    parameter = field.removesuffix("_bounds")
    bound = "下限" if path[4] == "0" else "上限"
    return ParameterCopy(
        f"{scenario_name}情景{parameter_names[parameter]}{bound}",
        f"中性值叠加情景宽度调整后，{scenario_name}情景{parameter_names[parameter]}超出范围时截断到该{bound}。",
    )


def _valuation_confidence_copy(leaf: str) -> ParameterCopy:
    entries = {
        "base": (
            "010 估值置信度起始分",
            "每次估值先从该分数开始，再按数据缺口、可用模型数量和模型分歧逐项扣分",
        ),
        "high_gap_penalty": (
            "每个高严重度缺口的估值置信度扣分",
            "每个高严重度输入缺口从估值置信度扣除该值",
        ),
        "medium_gap_penalty": (
            "每个中严重度缺口的估值置信度扣分",
            "每个中严重度输入缺口从估值置信度扣除该值",
        ),
        "low_gap_penalty": (
            "每个低严重度缺口的估值置信度扣分",
            "每个低严重度输入缺口从估值置信度扣除该值",
        ),
        "skipped_method_penalty": (
            "可用估值模型不足两个的置信度扣分",
            "成功计算的估值模型少于两个时，从估值置信度一次性扣除该值",
        ),
        "dispersion_penalty": (
            "估值模型分歧过大的置信度扣分",
            "模型中性结果最高值 / 最低值超过分歧倍数阈值时，从估值置信度一次性扣除该值",
        ),
        "minimum": ("010 估值置信度最终下限", "全部扣分完成后，置信度低于该值时抬高到此下限"),
        "maximum": ("010 估值置信度最终上限", "全部扣分完成后，置信度高于该值时压低到此上限"),
        "high_threshold": ("010 高置信度等级阈值", "最终估值置信度达到该值时标为高等级"),
        "medium_threshold": (
            "010 中置信度等级阈值",
            "最终估值置信度低于高等级阈值但达到该值时标为中等级，否则标为低等级",
        ),
    }
    label, description = entries[leaf]
    return ParameterCopy(label, f"{description}；等级只概括数据与模型完整度，不代表投资收益概率。")


def _price_copy(path: tuple[str, ...]) -> ParameterCopy:
    leaf = path[1]
    entries = {
        "safety_margin_min": (
            "011 可接受安全边际下限",
            "校验绑定 010 冻结的建议安全边际和用户手工覆盖值时使用的下限；低于该值会拒绝生成价格决策",
        ),
        "safety_margin_max": (
            "011 可接受安全边际上限",
            "校验绑定 010 冻结的建议安全边际和用户手工覆盖值时使用的上限，硬范围最高 100%；买入参考价 = 所选情景每股内在价值 × (1 - 生效安全边际)",
        ),
        "buy_price_scenario": (
            "011 建议买入价采用的内在价值情景",
            "从保守、中性、乐观三组买入参考价中选择哪一组作为“建议买入价”；默认中性，选择保守通常会给出更低参考价",
        ),
    }
    label, description = entries[leaf]
    return ParameterCopy(
        label, f"{description}；只影响新生成的 011 价格决策，当前价格仍只在 011 读取。"
    )
