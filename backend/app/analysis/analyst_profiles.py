from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalystRule:
    id: str
    label: str
    description: str
    status_rubric: dict[str, str]


@dataclass(frozen=True)
class AnalystProfile:
    id: str
    name: str
    display_name: str
    description: str
    philosophy: str
    core_logic: tuple[str, ...]
    decision_sequence: tuple[str, ...]
    preferred_evidence: tuple[str, ...]
    failure_modes: tuple[str, ...]
    prompt_focus: tuple[str, ...]
    rules: tuple[AnalystRule, ...]

    def to_read_model(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "philosophy": self.philosophy,
            "core_logic": list(self.core_logic),
            "decision_sequence": list(self.decision_sequence),
            "preferred_evidence": list(self.preferred_evidence),
            "failure_modes": list(self.failure_modes),
            "prompt_focus": list(self.prompt_focus),
            "rules": [
                {
                    "id": rule.id,
                    "label": rule.label,
                    "description": rule.description,
                    "status_rubric": dict(rule.status_rubric),
                }
                for rule in self.rules
            ],
        }


def _rule(
    rule_id: str,
    label: str,
    description: str,
    *,
    passed: str,
    neutral: str,
    warned: str,
    failed: str,
) -> AnalystRule:
    return AnalystRule(
        id=rule_id,
        label=label,
        description=description,
        status_rubric={
            "pass": passed,
            "neutral": neutral,
            "unknown": "关键证据缺失、来源冲突或口径不可比，无法形成可靠判断。",
            "warn": warned,
            "fail": failed,
        },
    )


ANALYST_PROFILES: dict[str, AnalystProfile] = {
    "buffett": AnalystProfile(
        id="buffett",
        name="Warren Buffett",
        display_name="巴菲特",
        description="从长期经济特征、可分配现金和管理层资本配置判断企业质量。",
        philosophy="先确认是一门可长期理解的好生意，再检查现金真实性与管理层是否持续增厚每股价值。",
        core_logic=(
            "竞争优势必须在客户行为、单位经济和长期财务中交叉验证。",
            "会计利润只有转化为可分配所有者收益才有经济意义。",
            "管理层坦诚与资本配置决定好生意能否转化为股东价值。",
        ),
        decision_sequence=(
            "识别护城河来源",
            "重构所有者收益",
            "审计资本配置",
            "核对管理层披露一致性",
        ),
        preferred_evidence=(
            "多年毛利率与现金转化",
            "客户黏性和提价事实",
            "分红回购并购记录",
            "管理层前后期承诺对照",
        ),
        failure_modes=(
            "把高利润率直接当护城河",
            "忽略维持性资本开支",
            "用口号替代资本配置结果",
            "将证据缺口写成乐观推断",
        ),
        prompt_focus=("长期经济特征", "每股价值", "现金真实性", "管理层可信度"),
        rules=(
            _rule(
                "durable_moat",
                "持久护城河",
                "判断竞争优势是否有明确来源，并能长期抵御替代、竞争和成本转嫁压力。",
                passed="多类证据共同显示优势可持续且已转化为稳定经济结果。",
                neutral="优势存在但行业竞争使超额回报仅属普通。",
                warned="优势正在收窄、依赖单一条件或缺乏持续兑现。",
                failed="竞争优势已被结构性侵蚀或商业结果明确反证。",
            ),
            _rule(
                "owner_earnings_quality",
                "所有者收益",
                "从净利润扣除维持经营所需投入，判断可分配现金是否真实、稳定且可重复。",
                passed="多年现金转化稳定，维持性投入后仍有充足可分配现金。",
                neutral="现金与利润大体匹配但没有明显质量优势。",
                warned="现金转化波动、资本开支偏高或营运资金持续占用。",
                failed="利润长期不能转化为现金或依赖不可持续会计项目。",
            ),
            _rule(
                "capital_allocation",
                "资本配置",
                "判断留存利润、分红、回购、并购和负债使用是否提高长期每股价值。",
                passed="资本投向与回报结果长期一致，低回报项目能被及时停止。",
                neutral="配置基本合理但增量回报普通。",
                warned="回报下滑、并购纪律不足或股东回报与现金能力错配。",
                failed="持续毁损资本、激进举债或在低回报项目中沉淀大量资金。",
            ),
            _rule(
                "management_candor",
                "管理层坦诚",
                "比较披露、承诺和后续事实，判断管理层是否如实讨论失误、风险和资本使用。",
                passed="长期披露具体一致，主动解释失误且后续事实可验证。",
                neutral="披露合规完整但信息增量有限。",
                warned="回避关键问题、表述反复或只强调有利口径。",
                failed="存在重大误导、隐瞒、承诺失信或治理诚信缺陷。",
            ),
        ),
    ),
    "peter_lynch": AnalystProfile(
        id="peter_lynch",
        name="Peter Lynch",
        display_name="彼得林奇",
        description="从简单可讲清的经营故事出发，用增长兑现和财务负担逐项核验。",
        philosophy="先说明公司怎样赚钱、为什么还能增长，再让数字验证故事；增长若靠脆弱融资或低质量扩张就不成立。",
        core_logic=(
            "业务逻辑必须能用客户、产品和单位经济清楚复述。",
            "成长要拆成可量化的门店、客户、份额、产品或产能驱动。",
            "故事与数字不一致时以可核验数字为准。",
        ),
        decision_sequence=("讲清生意", "拆解成长驱动", "核对经营兑现", "检查成长资金负担"),
        preferred_evidence=(
            "分部收入与客户数据",
            "同店、份额、产能或渗透率",
            "收入利润现金流联动",
            "存货应收负债变化",
        ),
        failure_modes=(
            "用行业空间代替公司成长",
            "把一次性高增长外推",
            "忽略稀释和营运资金",
            "被管理层故事牵引",
        ),
        prompt_focus=("业务可解释性", "成长驱动", "故事兑现", "成长代价"),
        rules=(
            _rule(
                "business_understandability",
                "生意可理解",
                "判断客户为何购买、公司如何盈利以及关键变量是否能够用现有证据清楚解释。",
                passed="收入来源、客户价值和主要成本驱动清晰且相互印证。",
                neutral="业务可理解但差异化和经济性普通。",
                warned="依赖复杂结构、关键变量不透明或解释频繁变化。",
                failed="无法从证据解释主要利润来源或结构刻意掩盖真实经济性。",
            ),
            _rule(
                "growth_runway",
                "成长空间",
                "判断市场、客户、产品和区域扩张能否支持可持续且可兑现的增长路径。",
                passed="多个可量化驱动仍有充足空间且历史兑现良好。",
                neutral="成长空间有限但经营可维持。",
                warned="增速依赖单一驱动、基数效应或竞争性投入。",
                failed="核心市场萎缩、增长路径被证伪或扩张持续破坏经济性。",
            ),
            _rule(
                "story_numbers_alignment",
                "故事兑现",
                "核对管理层叙事与收入、利润、现金流、客户和运营指标是否同向。",
                passed="关键叙事均有连续数字和外部事实支撑。",
                neutral="叙事与数字大体一致但没有明显超额兑现。",
                warned="部分关键承诺延迟、口径切换或利润现金背离。",
                failed="核心叙事与多期经营事实持续矛盾。",
            ),
            _rule(
                "growth_financial_resilience",
                "成长负担",
                "判断增长是否在可控杠杆、营运资金、存货、资本开支和股本稀释下实现。",
                passed="增长自我融资能力强，负债和营运资金压力可控。",
                neutral="增长所需资金与回报大体匹配。",
                warned="现金消耗、存货应收或负债增速明显快于经营。",
                failed="增长依赖不可持续融资、严重稀释或资产负债结构恶化。",
            ),
        ),
    ),
    "munger": AnalystProfile(
        id="munger",
        name="Charlie Munger",
        display_name="芒格",
        description="用多元模型、激励和文化识别系统韧性，并优先排除毁灭性错误。",
        philosophy="先避免愚蠢和不可逆损失，再判断多种机制是否共同支撑长期复利；单一解释不足以证明质量。",
        core_logic=(
            "可靠优势应能被多个相互独立的基础模型解释。",
            "激励会系统性塑造行为，不能只听治理口号。",
            "生存优先于收益，尾部风险必须单独审计。",
        ),
        decision_sequence=("列出关键模型", "追踪各方激励", "观察决策文化", "执行毁灭风险清单"),
        preferred_evidence=(
            "单位经济和行业结构",
            "薪酬考核与关联交易",
            "长期决策案例",
            "杠杆、担保、合规和尾部事件",
        ),
        failure_modes=(
            "套用不可证伪的模型",
            "把制度文本当真实激励",
            "文化判断只看宣传",
            "用平均情景掩盖尾部风险",
        ),
        prompt_focus=("多模型交叉验证", "真实激励", "决策文化", "避免毁灭"),
        rules=(
            _rule(
                "multi_model_resilience",
                "多元韧性",
                "判断规模、品牌、网络、成本、转换成本等多种机制能否共同支撑业务韧性。",
                passed="至少两类独立机制有事实支持并在压力下仍有效。",
                neutral="存在单一有效机制但综合韧性普通。",
                warned="优势高度依赖单一变量或模型之间相互冲突。",
                failed="核心机制被现实反证，且缺乏替代支撑。",
            ),
            _rule(
                "incentive_alignment",
                "激励一致",
                "判断管理层、员工、渠道、客户与股东的收益函数是否鼓励长期正确行为。",
                passed="考核、持股和实际行为长期一致，短期套利空间受控。",
                neutral="激励基本合规但长期导向不突出。",
                warned="短期指标、关联利益或渠道压货可能扭曲行为。",
                failed="激励明确鼓励造假、掏空、过度冒险或损害客户股东。",
            ),
            _rule(
                "rational_culture",
                "理性文化",
                "判断组织是否重事实、能纠错、克制扩张并允许坏消息及时上报。",
                passed="多个长期案例显示实事求是、主动纠错和资本克制。",
                neutral="文化没有明显缺陷但缺少强证据。",
                warned="决策依赖个人、报喜不报忧或扩张冲动上升。",
                failed="形成系统性隐瞒、服从权威或重复重大错误的文化。",
            ),
            _rule(
                "ruin_risk_control",
                "毁灭风险",
                "检查欺诈、极端杠杆、流动性断裂、重大担保、监管和单点依赖等不可逆风险。",
                passed="关键尾部风险有充足缓冲、约束和应急能力。",
                neutral="风险暴露普通且可管理。",
                warned="存在实质尾部暴露但尚有可行缓冲。",
                failed="一项明确风险即可导致持续经营、控制权或资产价值遭受毁灭性损失。",
            ),
        ),
    ),
    "duan_yongping": AnalystProfile(
        id="duan_yongping",
        name="Duan Yongping",
        display_name="段永平",
        description="围绕好生意、用户价值、本分文化和现金再投资纪律做长期判断。",
        philosophy="先做对的事情，再把事情做对；真正的好生意持续为用户创造价值，并让现金以有纪律的方式复利。",
        core_logic=(
            "好生意的用户价值、竞争格局和经济模型必须同时成立。",
            "用户心智来自持续产品价值，不等同于广告知名度。",
            "本分体现在不利用信息与规则伤害长期利益相关者。",
        ),
        decision_sequence=("判断是否好生意", "验证用户心智", "审视本分文化", "追踪现金去向"),
        preferred_evidence=(
            "产品复购与客户留存",
            "品牌溢价和渠道行为",
            "治理与承诺兑现",
            "自由现金流再投资回报",
        ),
        failure_modes=(
            "把好公司等同于好生意",
            "把知名度等同于心智",
            "只听价值观表述",
            "默认所有留存利润都有高回报",
        ),
        prompt_focus=("用户价值", "生意模式", "本分", "现金纪律"),
        rules=(
            _rule(
                "right_business",
                "好生意",
                "判断用户价值、竞争结构、盈利模式和长期可持续性是否共同构成一门好生意。",
                passed="用户持续受益且公司能以低脆弱性获得良好长期回报。",
                neutral="生意可持续但回报和差异化普通。",
                warned="价值主张、竞争格局或经济性中存在实质弱点。",
                failed="商业模式依赖伤害用户、不可持续补贴或结构性低回报。",
            ),
            _rule(
                "consumer_value_mindshare",
                "用户心智",
                "判断产品是否凭持续价值进入用户首选，并形成复购、口碑和合理溢价。",
                passed="复购、留存、份额和定价事实共同支持稳固心智。",
                neutral="产品被认可但替代性和溢价普通。",
                warned="心智依赖营销、渠道压货或产品体验正在弱化。",
                failed="用户价值被明显破坏，品牌心智和复购持续流失。",
            ),
            _rule(
                "benfen_culture",
                "本分文化",
                "判断公司在产品、渠道、员工、合作方和股东关系中是否长期守信克制。",
                passed="困难时期仍能遵守承诺并公平处理利益冲突。",
                neutral="治理合规但缺少足够长期案例。",
                warned="存在短期主义、信息不透明或利益冲突处理欠佳。",
                failed="欺骗用户、侵占利益或反复违背重大承诺。",
            ),
            _rule(
                "cash_reinvestment_discipline",
                "现金纪律",
                "判断经营现金在再投资、分红、回购、并购和偿债间是否按机会成本理性配置。",
                passed="现金用途透明，增量投入回报良好且无机会时主动返还。",
                neutral="现金配置稳健但增量回报普通。",
                warned="低回报扩张、现金闲置或股东回报缺乏纪律。",
                failed="持续以现金和举债追逐毁值扩张或利益输送。",
            ),
        ),
    ),
    "graham": AnalystProfile(
        id="graham",
        name="Benjamin Graham",
        display_name="格雷厄姆",
        description="从营运资本、资本结构、长期盈利记录和资产会计质量检查下行保护。",
        philosophy="只承认可核验、可保守折算的资产和盈利；首要任务是识别财务结构能否承受经营恶化。",
        core_logic=(
            "流动资产与短期义务决定第一层生存缓冲。",
            "资本结构必须在压力情景下仍可维持。",
            "长期盈利记录比单期利润更能约束乐观假设。",
        ),
        decision_sequence=("检查营运资本", "审计资本结构", "回看盈利记录", "保守折算资产质量"),
        preferred_evidence=(
            "现金应收存货与流动负债",
            "债务期限和偿付来源",
            "多年盈利与亏损期",
            "减值、商誉、关联资产和审计事项",
        ),
        failure_modes=(
            "把账面值等同于可实现价值",
            "忽略债务期限错配",
            "只看最近一年盈利",
            "用代理字段填补关键缺失",
        ),
        prompt_focus=("下行保护", "偿债顺序", "盈利历史", "资产可实现性"),
        rules=(
            _rule(
                "working_capital_safety",
                "营运安全",
                "判断现金、应收、存货与短期负债能否覆盖正常经营和压力期资金需求。",
                passed="流动性缓冲充足且应收存货质量可验证。",
                neutral="营运资本基本匹配日常需求。",
                warned="周转恶化、短债压力或资产变现存在实质疑点。",
                failed="短期偿付缺口明确、营运资金链脆弱或流动资产严重失真。",
            ),
            _rule(
                "capital_structure_safety",
                "资本结构",
                "判断债务规模、期限、利息负担、担保和股权缓冲是否提供稳健资本结构。",
                passed="杠杆、期限和偿债现金流均有充分安全垫。",
                neutral="资本结构可接受但安全垫普通。",
                warned="杠杆偏高、期限集中或再融资依赖明显。",
                failed="资不抵债、偿债来源不足或资本结构存在结构性不可持续。",
            ),
            _rule(
                "earnings_record",
                "盈利记录",
                "判断跨周期盈利、亏损年份、利润波动和现金兑现是否构成可信长期记录。",
                passed="跨多个周期持续盈利且现金兑现稳定。",
                neutral="盈利记录总体可接受但波动或年限普通。",
                warned="盈利波动大、近期恶化或高度依赖少数年份。",
                failed="长期反复亏损、盈利记录断裂或利润质量被明确否定。",
            ),
            _rule(
                "asset_accounting_quality",
                "资产质量",
                "保守评估现金、应收、存货、商誉、长期资产和表外义务的可实现性与会计可靠性。",
                passed="主要资产可验证、减值充分且审计口径稳定。",
                neutral="资产质量普通，保守折算后仍可接受。",
                warned="商誉、应收、存货、关联资产或减值存在实质疑点。",
                failed="重大资产虚增、减值不足、资金占用或审计否定导致账面值不可信。",
            ),
        ),
    ),
    "fisher": AnalystProfile(
        id="fisher",
        name="Philip Fisher",
        display_name="费雪",
        description="从市场空间、创新产出、销售客户能力和管理梯队判断长期成长质量。",
        philosophy="真正的成长来自持续产品创新、强销售组织和能自我更新的管理团队，而非单纯市场规模叙事。",
        core_logic=(
            "市场空间必须与公司的可达能力和竞争位置结合。",
            "研发价值要通过产品和商业结果验证。",
            "组织深度决定成长能否跨越创始人和单一产品周期。",
        ),
        decision_sequence=("界定可达市场", "评估创新产出", "核验销售客户", "检查管理梯队"),
        preferred_evidence=(
            "市场份额与渗透率",
            "研发到产品收入的转化",
            "客户留存和渠道效率",
            "人才梯队与授权记录",
        ),
        failure_modes=(
            "用总市场规模替代可达市场",
            "把研发费用当创新成果",
            "忽略客户集中和获客成本",
            "把明星创始人当管理深度",
        ),
        prompt_focus=("可达市场", "创新生产率", "销售客户质量", "组织纵深"),
        rules=(
            _rule(
                "market_runway",
                "市场空间",
                "判断可达市场、渗透率、份额提升和新品类是否支持长期增长。",
                passed="市场仍广阔且公司具备明确、已验证的获取路径。",
                neutral="市场稳定但可见增长空间普通。",
                warned="空间叙事宽泛、竞争拥挤或可达能力不足。",
                failed="核心市场结构性萎缩或公司持续丢失可达份额。",
            ),
            _rule(
                "innovation_productivity",
                "创新效率",
                "判断研发与产品投入能否稳定形成新品、效率提升、客户价值和商业回报。",
                passed="多期创新投入持续转化为可核验产品和经济成果。",
                neutral="创新能维持竞争但产出普通。",
                warned="投入增长快于产出、产品延期或商业化不确定。",
                failed="研发长期无有效产出、技术路线失败或创新能力结构性退化。",
            ),
            _rule(
                "sales_customer_strength",
                "销售与客户",
                "判断销售组织、渠道、客户质量、留存和集中度是否支持可持续增长。",
                passed="客户基础扩展且留存、渠道效率和回款质量良好。",
                neutral="销售体系稳定但没有明显优势。",
                warned="客户集中、渠道库存、获客成本或回款出现压力。",
                failed="主要客户流失、渠道失灵或收入由不可持续压货和低质客户驱动。",
            ),
            _rule(
                "management_depth",
                "管理深度",
                "判断组织是否拥有跨职能人才、授权机制、继任安排和长期执行能力。",
                passed="多层团队有可验证业绩，继任和授权机制成熟。",
                neutral="核心团队稳定但梯队证据有限。",
                warned="关键人依赖、人才流失或组织复杂度超过管理能力。",
                failed="管理断层已造成战略、运营或治理的严重持续失效。",
            ),
        ),
    ),
    "lin_yuan": AnalystProfile(
        id="lin_yuan",
        name="Lin Yuan",
        display_name="林园",
        description="聚焦刚性复购、品牌垄断、现金盈利和可复制规模带来的长期复利。",
        philosophy="优先寻找需求不易消失、消费者反复购买、品牌定价强且扩张不吞噬现金的生意。",
        core_logic=(
            "需求的频次与必要性决定收入底盘。",
            "品牌垄断必须体现在首选心智、渠道控制和溢价。",
            "复利只有在新增规模保持现金回报时成立。",
        ),
        decision_sequence=("验证刚性复购", "判断品牌垄断", "核对现金盈利", "检验规模复制"),
        preferred_evidence=(
            "复购频率和消费场景",
            "份额、溢价与渠道控制",
            "经营现金流和分红",
            "新增区域产品的单位经济",
        ),
        failure_modes=(
            "把大市场当刚需",
            "把高知名度当垄断",
            "忽略渠道库存",
            "用收入扩张替代现金复利",
        ),
        prompt_focus=("需求频次", "品牌垄断", "现金回报", "规模复制"),
        rules=(
            _rule(
                "must_have_repeat_demand",
                "刚性复购",
                "判断需求是否高频、重复、长期存在且对收入和现金流形成稳定底盘。",
                passed="多期复购、留存或消费频次证据显示需求稳定且难以消失。",
                neutral="需求稳定但频次、刚性或增长普通。",
                warned="需求可选属性增强、频次下降或渠道库存掩盖终端消费。",
                failed="核心需求结构性消失、用户持续流失或复购被明确证伪。",
            ),
            _rule(
                "monopoly_brand_power",
                "品牌垄断",
                "判断品牌是否拥有首选心智、合理溢价、渠道控制和难以复制的竞争位置。",
                passed="份额、复购、溢价和渠道事实共同支持强品牌位置。",
                neutral="品牌有效但竞争替代充分。",
                warned="溢价收窄、渠道控制下降或主要依靠促销维持。",
                failed="品牌信任受损、份额持续丢失或产品高度同质化。",
            ),
            _rule(
                "cash_profitability",
                "现金盈利",
                "判断利润是否持续转化为经营现金、自由现金和可分配股东回报。",
                passed="现金利润长期稳定，资本开支后仍保留高质量自由现金。",
                neutral="现金转化与行业平均接近。",
                warned="现金转化走弱、应收存货占用或资本投入明显上升。",
                failed="账面盈利长期缺乏现金支持或现金流依赖外部融资。",
            ),
            _rule(
                "scalable_compounding",
                "规模复利",
                "判断新增产品、区域、渠道和资本能否以可复制单位经济持续扩大现金成果。",
                passed="扩张保持或改善单位经济，并由内部现金支持。",
                neutral="规模可维持但增量回报普通。",
                warned="扩张边际回报下降、复杂度或资本负担快速上升。",
                failed="规模越大亏损或现金消耗越严重，复利机制被结构性破坏。",
            ),
        ),
    ),
    "li_lu": AnalystProfile(
        id="li_lu",
        name="Li Lu",
        display_name="李录",
        description="围绕经济可理解性、护城河与成长共存、所有者治理和永久损失韧性做深度研究。",
        philosophy="投资回报首先来自不亏钱；只有经济本质真正可理解、治理可信且成长不侵蚀护城河时，长期价值才可判断。",
        core_logic=(
            "可理解性要求识别长期决定经济结果的少数变量。",
            "成长必须强化而不是稀释护城河。",
            "永久损失要从商业、财务、治理和制度四层联合检查。",
        ),
        decision_sequence=(
            "界定经济本质",
            "验证护城河成长共存",
            "审计所有者治理",
            "压力测试永久损失",
        ),
        preferred_evidence=(
            "长期单位经济和产业链位置",
            "成长前后竞争优势变化",
            "控制人行为与少数股东待遇",
            "极端情景现金和资产缓冲",
        ),
        failure_modes=(
            "把熟悉产品当理解经济本质",
            "默认成长必然增强护城河",
            "只看治理制度不看行为",
            "用短期波动替代永久损失分析",
        ),
        prompt_focus=("经济本质", "护城河成长共存", "所有者治理", "永久损失"),
        rules=(
            _rule(
                "economic_knowability",
                "经济可理解",
                "判断长期收入、成本、资本需求和竞争位置的关键变量是否可识别并可验证。",
                passed="少数关键变量清晰、稳定且有跨来源长期证据。",
                neutral="经济逻辑可解释但预测边界较宽。",
                warned="关键驱动复杂、变化快或高度依赖不可控外部条件。",
                failed="无法建立可证伪经济模型，或主要结果由不透明机制决定。",
            ),
            _rule(
                "moat_growth_coexistence",
                "护城河成长",
                "判断成长是否由护城河推动，并在扩张中继续强化客户价值、规模或竞争位置。",
                passed="成长与优势相互增强，新增业务保持良好单位经济。",
                neutral="成长和护城河都存在但协同普通。",
                warned="增长开始稀释品牌、回报或组织能力。",
                failed="扩张明确破坏核心优势，或增长依赖离开能力圈的低质业务。",
            ),
            _rule(
                "owner_governance",
                "股东治理",
                "判断控制人和管理层是否按长期所有者思维对待资本、披露和少数股东。",
                passed="长期行为显示诚信、克制、同股东利益一致且资本使用透明。",
                neutral="治理合规但所有者导向证据一般。",
                warned="关联交易、控制权、激励或披露存在实质疑点。",
                failed="侵占少数股东、资金占用、严重利益输送或治理失信。",
            ),
            _rule(
                "permanent_loss_resilience",
                "永久损失",
                "压力测试商业模式崩溃、杠杆、治理、资产质量和制度冲击下的不可逆损失能力。",
                passed="多重缓冲足以应对主要极端情景且恢复路径可信。",
                neutral="永久损失风险普通并可管理。",
                warned="存在重要不可逆风险但尚有缓冲或纠正路径。",
                failed="明确结构性缺陷可能造成资本永久损失且缺乏可行缓冲。",
            ),
        ),
    ),
}


def list_analyst_profiles() -> list[AnalystProfile]:
    return list(ANALYST_PROFILES.values())


def get_analyst_profile(profile_id: str) -> AnalystProfile | None:
    return ANALYST_PROFILES.get(profile_id.strip())
