from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalystRule:
    id: str
    label: str
    description: str


@dataclass(frozen=True)
class AnalystProfile:
    id: str
    name: str
    display_name: str
    description: str
    philosophy: str
    rules: tuple[AnalystRule, ...]
    prompt_focus: tuple[str, ...]

    def to_read_model(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "philosophy": self.philosophy,
            "rules": [
                {
                    "id": rule.id,
                    "label": rule.label,
                    "description": rule.description,
                }
                for rule in self.rules
            ],
            "prompt_focus": list(self.prompt_focus),
        }


ANALYST_PROFILES: dict[str, AnalystProfile] = {
    "buffett": AnalystProfile(
        id="buffett",
        name="Warren Buffett",
        display_name="巴菲特",
        description="从护城河、长期盈利质量、管理层可信度和安全边际看公司。",
        philosophy="只在证据支持的范围内判断企业长期经济特征，不给买卖或仓位建议。",
        rules=(
            AnalystRule("moat", "护城河", "业务是否具备可持续竞争优势和定价能力。"),
            AnalystRule("quality", "盈利质量", "利润是否由稳定现金流和高质量资产支撑。"),
            AnalystRule("management", "管理层", "公告和历史记录是否体现审慎、透明和股东友好。"),
            AnalystRule("margin_of_safety", "安全边际", "财务和外部证据是否暴露估值容错空间不足。"),
        ),
        prompt_focus=("长期业务质量", "资本回报", "现金流质量", "风险容错"),
    ),
    "peter_lynch": AnalystProfile(
        id="peter_lynch",
        name="Peter Lynch",
        display_name="彼得林奇",
        description="从可理解业务、成长路径、行业景气和财务兑现度看公司。",
        philosophy="先理解生意和增长来源，再核对财务是否兑现，不把热门叙事当作结论。",
        rules=(
            AnalystRule("understandable_business", "可理解业务", "业务模式和增长驱动是否清楚。"),
            AnalystRule("growth_runway", "成长空间", "收入、利润或行业证据是否支持持续成长。"),
            AnalystRule("story_vs_numbers", "故事与数字", "公司叙事是否被财务数据和公告验证。"),
            AnalystRule(
                "balance_sheet_risk",
                "资产负债风险",
                "成长背后是否存在杠杆、现金流或存货压力。",
            ),
        ),
        prompt_focus=("业务故事", "增长兑现", "行业景气", "财务风险"),
    ),
    "munger": AnalystProfile(
        id="munger",
        name="Charlie Munger",
        display_name="芒格",
        description="从多学科模型、激励机制、企业文化和极端风险看公司。",
        philosophy="先避免明显错误，再寻找长期高质量生意；对激励和文化保持敏感。",
        rules=(
            AnalystRule("mental_models", "多元模型", "业务优势是否可被多个基础模型解释。"),
            AnalystRule("incentives", "激励机制", "管理层、渠道和客户激励是否与长期价值一致。"),
            AnalystRule("culture", "企业文化", "公告和历史记录是否体现长期主义和理性决策。"),
            AnalystRule(
                "avoid_stupidity",
                "不碰清单",
                "是否出现诚信、杠杆、复杂度或尾部风险信号。",
            ),
        ),
        prompt_focus=("多元模型", "激励机制", "企业文化", "极端风险"),
    ),
    "duan_yongping": AnalystProfile(
        id="duan_yongping",
        name="Duan Yongping",
        display_name="段永平",
        description="从生意模式、企业文化、消费者心智和长期自由现金流看公司。",
        philosophy="先判断生意好坏和企业本分，再看长期现金流是否能持续。",
        rules=(
            AnalystRule("business_quality", "生意模式", "生意是否简单、可持续且具备长期价值。"),
            AnalystRule("benfen_culture", "本分文化", "公告和行为是否体现诚信、克制和长期主义。"),
            AnalystRule("consumer_mindshare", "消费者心智", "产品力、品牌或差异化是否被证据支持。"),
            AnalystRule(
                "shareholder_return",
                "股东回报",
                "现金流、回购或分红是否体现长期资本配置质量。",
            ),
        ),
        prompt_focus=("生意模式", "企业文化", "产品心智", "自由现金流"),
    ),
    "graham": AnalystProfile(
        id="graham",
        name="Benjamin Graham",
        display_name="格雷厄姆",
        description="从资产保护、盈利稳定性、保守假设和安全边际看公司。",
        philosophy="优先避免永久性损失，要求结论建立在保守、可验证的数据上。",
        rules=(
            AnalystRule("asset_protection", "资产保护", "资产、负债和现金流是否提供下行保护。"),
            AnalystRule("earnings_stability", "盈利稳定性", "盈利是否穿越周期且波动可解释。"),
            AnalystRule("conservatism", "保守假设", "证据不足时是否保持未知而非乐观推断。"),
            AnalystRule(
                "valuation_discipline",
                "估值纪律",
                "是否存在明显不支持高预期的财务或公告信号。",
            ),
        ),
        prompt_focus=("下行保护", "盈利稳定", "保守判断", "安全边际"),
    ),
    "fisher": AnalystProfile(
        id="fisher",
        name="Philip Fisher",
        display_name="费雪",
        description="从长期成长质量、研发/产品、销售组织和管理能力看公司。",
        philosophy="寻找能长期扩大市场和改进产品的高质量成长企业，同时记录待调研问题。",
        rules=(
            AnalystRule("long_term_growth", "长期成长", "公司是否有长期市场扩张和产品升级证据。"),
            AnalystRule("innovation", "创新能力", "公告和证据是否体现研发、产品或技术优势。"),
            AnalystRule("sales_execution", "销售执行", "收入增长是否有渠道、客户或市场份额支撑。"),
            AnalystRule("management_depth", "管理深度", "管理层是否展现长期投入和组织能力。"),
        ),
        prompt_focus=("成长质量", "研发产品", "销售执行", "管理能力"),
    ),
    "lin_yuan": AnalystProfile(
        id="lin_yuan",
        name="Lin Yuan",
        display_name="林园",
        description="从消费刚需、品牌壁垒、现金创造和长期复利能力看公司。",
        philosophy="偏好能长期赚钱、现金流扎实、品牌或渠道壁垒清晰的生意。",
        rules=(
            AnalystRule("must_have_demand", "刚性需求", "产品或服务是否具备持续、重复消费属性。"),
            AnalystRule("brand_power", "品牌壁垒", "品牌、渠道或用户心智是否形成竞争壁垒。"),
            AnalystRule("cash_generation", "现金创造", "利润是否能转化为稳定现金流和分红能力。"),
            AnalystRule("compounding", "复利能力", "历史数据是否支持长期扩大经营成果。"),
        ),
        prompt_focus=("消费属性", "品牌渠道", "现金创造", "长期复利"),
    ),
    "li_lu": AnalystProfile(
        id="li_lu",
        name="Li Lu",
        display_name="李录",
        description="从能力圈、深度研究、长期内在价值和永久性损失风险看公司。",
        philosophy="要求关键事实足够扎实，重视反方证据和下行风险。",
        rules=(
            AnalystRule("circle_of_competence", "能力圈", "当前快照是否足以支持理解这门生意。"),
            AnalystRule("depth_of_research", "研究充分度", "财务、公告和证据是否覆盖关键事实。"),
            AnalystRule("intrinsic_value", "内在价值线索", "长期现金流和竞争位置是否有明确证据。"),
            AnalystRule("permanent_loss", "永久损失", "是否存在不可逆损失、治理或资产质量风险。"),
        ),
        prompt_focus=("能力圈", "关键事实", "反方证据", "永久损失"),
    ),
    "ray_dalio": AnalystProfile(
        id="ray_dalio",
        name="Ray Dalio",
        display_name="瑞达利欧",
        description="从宏观周期、信用环境、通胀利率和公司脆弱点看公司。",
        philosophy="把公司放进宏观和周期环境中识别风险暴露，不输出仓位建议。",
        rules=(
            AnalystRule(
                "macro_sensitivity",
                "宏观敏感度",
                "业务是否受利率、通胀、汇率或商品价格影响。",
            ),
            AnalystRule("cycle_position", "周期位置", "财务和公告是否显示顺周期或逆周期特征。"),
            AnalystRule("credit_liquidity", "信用流动性", "负债、现金流和融资环境是否构成压力。"),
            AnalystRule(
                "portfolio_risk_signal",
                "组合风险信号",
                "是否暴露单一宏观因子或共同风险。",
            ),
        ),
        prompt_focus=("宏观周期", "信用环境", "通胀利率", "风险暴露"),
    ),
    "george_soros": AnalystProfile(
        id="george_soros",
        name="George Soros",
        display_name="乔治索罗斯",
        description="从反身性、预期偏差、宏观脆弱点和反方证据看公司。",
        philosophy="识别基本面叙事与现实反馈之间的偏差，只输出风险和验证问题，不给交易动作。",
        rules=(
            AnalystRule(
                "reflexivity",
                "反身性",
                "公司叙事、市场预期和经营反馈是否可能相互强化或反向修正。",
            ),
            AnalystRule(
                "narrative_gap",
                "预期偏差",
                "公告、财务和外部证据是否显示叙事与实际经营之间存在偏差。",
            ),
            AnalystRule(
                "macro_fragility",
                "宏观脆弱点",
                "业务是否受信用、流动性、监管、汇率或周期冲击放大影响。",
            ),
            AnalystRule(
                "counter_evidence",
                "反方证据",
                "哪些事实最可能推翻当前主流乐观或悲观叙事。",
            ),
        ),
        prompt_focus=("反身性", "预期偏差", "宏观脆弱点", "反方证据"),
    ),
}


def list_analyst_profiles() -> list[AnalystProfile]:
    return list(ANALYST_PROFILES.values())


def get_analyst_profile(profile_id: str) -> AnalystProfile | None:
    return ANALYST_PROFILES.get(profile_id.strip())
