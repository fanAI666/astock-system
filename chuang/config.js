'use strict';
// chuang/config.js — 双创选股策略 · 全参数配置中心
// 目标：把原先散落在 backtest_chuang.js 顶部的硬编码常量 + env 开关，集中为单一可配置对象。
// 兼容旧 env：BT_SRC / BT_OUT / BT_FUND / BT_GRID / BT_BASKET / BT_K / BT_H / BT_R /
//             CHUANG_GATES / CHUANG_EXEC / FUND_SRC / FUND_OUT / FUND_CODES / FUND_SKIP_G6。
// 新增指标层（PE/PB/营收增长/MACD）默认全部关闭 —— 保证重构后回测行为与旧版严格一致（parity）。

const env = process.env;

function boolEnv(name, def) {
  const v = env[name];
  if (v === undefined || v === '') return def;
  return v !== '0' && v !== 'false' && v !== 'no';
}
function numEnv(name, def) {
  const v = env[name];
  if (v === undefined || v === '') return def;
  const n = +v;
  return isFinite(n) ? n : def;
}
// 本地日期 YYYYMMDD（不要用 toISOString，UTC 会在 08:00 前把日期退一天）
function todayYmd() {
  const d = new Date(), p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`;
}

const CHUANG_CONFIG = {
  // ===== 数据源（与旧 BT_* env 兼容）=====
  // 默认切到全宇宙 universe_klines.json（1270 支）：
  // ① signals 不再因 import_final.json 仅 18 支双创而恒出 0 → 双创 Tab 不再空白；
  // ② backtest 不带 BT_SRC 时也默认扫全宇宙，避免 n=0 事故。需窄池时显式 BT_SRC=import_final.json。
  src: env.BT_SRC || 'D:/WorkBuddy/选股结果/universe_klines.json',
  out: env.BT_OUT || 'D:/WorkBuddy/选股结果/backtest_chuang.json',
  fundFile: env.BT_FUND || 'D:/WorkBuddy/选股结果/fundamental.json',
  indexFile: 'D:/WorkBuddy/选股结果/index_sh.json',

  // ===== 回测区间 =====
  // to 默认滚动到「今天」，避免写死日期后长期滞后导致近月信号被区间右端截断
  // （2026-08-06 前写死 20260630，已滞后 5 周）。需复现历史结果时用 BT_TO=20260630 覆盖。
  period: { from: env.BT_FROM || '20230828', to: env.BT_TO || todayYmd() },

  // ===== 板块门控：主板完全不动；仅 chuang_only 走 G/E 体系 =====
  boards: 'chuang_only',
  chuangBoards: ['cyb', 'kcb', 'kc'],

  // ===== 主板固定参数（重构后保持原样，任何路径都不改主板）=====
  main: { stop: 0.02, profit: 0.06, kAtr: 1.05, maxHold: 20, tol: 0.02, trailPct: 0.03, trailCap: 0.06 },

  // ===== 双创 G1–G5 选股门（默认开启，保留核心逻辑）=====
  gates: {
    enabled: boolEnv('CHUANG_GATES', true),
    G1_liquidityFloor: 1.0e8,                 // G1 流动性：近20日日均成交额 ≥ 1亿元
    G2_atrMin: 0.03, G2_atrMax: 0.06,         // G2 波动率带：入场日 ATR14% ∈ [3%,6%]
    G3_ma20ExtMax: 0.12, G3_rsiLo: 40, G3_rsiHi: 65, // G3 动量洁净度：距MA20∈[0,+12%] 且 RSI∈[40,65]
    G3_ma20ExtMinInvert: -0.35,               // 5.0 反手：镜像入场带 = 距MA20∈[-35%,0]（深跌坑）
    G4_relativeStrength: true,                // G4 相对强度：个股20日收益 > 上证同期
    G5_earningsQuality: true,                 // G5 盈利质量：读边车 g5Quality===false 才剔除整只
  },

  // ===== 因子层（2026-08-12 因子挖掘 14 轮验证唯一存活因子；默认关 → 回测 parity 不变）=====
  // 因子：idioVol60(low) = 低特质波动（对市场等权收益 60 日滚动回归残差的年化波动，取每日最低 maxPct 比例）
  // 定位：最外层主筛（先于 TLS/preFilter/gates/veto），只缩池不改任何持有期/止损/止盈规则。
  // 证据链（详见 chuang/factors.js 头部注释 + 选股结果/factor_*.json）：
  //   R1  横截面 RankIC = -0.0936 / ICIR = -0.52（h=20，负号 → 低波更优），441 个交易日
  //   R10b 流动性中性池内 36.28% 胜率 / +0.773%/笔 / PF1.61  vs 同池随机 31.11% / +0.465% / PF1.34
  //   R11 生产级流动性池(≥1亿) 35.32% / +0.669% / PF1.52，holdout +0.163 vs 随机 +0.032
  //   R14 block-bootstrap ×1000：期望差 +0.35~0.39pp，95%CI [0.18,0.60]，P(差>0)=1.000
  // 短板：分年度 2024 +0.343% / 2025 +0.417% / 2026YTD -0.349% → 相对优势稳定但绝对期望在弱市为负。
  // 故默认 enabled=false，等中报季 5.7 闸门用真实数据定夺；验证用 CHUANG_FACTORS=1 显式开启。
  factors: {
    enabled: boolEnv('CHUANG_FACTORS', false),
    universeFile: 'D:/WorkBuddy/选股结果/universe_klines.json',
    idioVolWindow: numEnv('CHUANG_FACTOR_WIN', 60),   // 特质波动回归窗口（日）
    minBars: 250,                                     // 次新股护栏（与 build_08xx.py 的 MIN_BARS 同口径）
    maxPct: numEnv('CHUANG_FACTOR_PCT', 0.30),        // 每日保留 idioVol 最低的比例（R10/R11 均用 30%）
    minKeep: 30,                                      // 比例过小时的保底只数
    minCrossSection: 60,                              // 当日横截面样本 < 60 支则本日不启用因子筛（避免小样本噪声）
    minTurnover: 1.0e8,                               // 与 G1 同口径的流动性下限，防低流动性边界套利（R6 结论）
  },

  // ===== 波动率目标叠加层（P1，2026-08-17；risk-overlay，默认关）=====
  // 高波动 regime 暂停入场，不改选股/止损/止盈规则。绝对阈值(abs)/z 分数(z) 两模式，env 可切。
  // 验证假设「择时贡献 > 选股」（详见 chuang/voltarget.js 头部）。回测 parity：enabled=false 时不调用。
  volTarget: {
    enabled: boolEnv('CHUANG_VOLTARGET', false),
    universeFile: 'D:/WorkBuddy/选股结果/universe_klines.json',
    mode: process.env.CHUANG_VT_MODE || 'abs',            // 'abs'（年化波动阈值）| 'z'（滚动 z 分数）
    window: numEnv('CHUANG_VT_WIN', 60),                  // 滚动波动窗（日）
    volPause: numEnv('CHUANG_VT_VOL', 0.40),              // abs 模式：板块年化波动 > 40% 暂停
    zThresh: numEnv('CHUANG_VT_Z', 1.5),                  // z 模式阈值
    zLook: numEnv('CHUANG_VT_ZLOOK', 250),                // z 模式历史回看窗
  },

  // ===== 5.0 反手证伪开关（圆桌决策：一锤定音"方向反了 vs 带宽错配"）=====
  // 开启后：仅翻转动量入场极性（G3 由"站上MA20且距MA20∈[0,+12%]"→"跌破MA20且∈[-35%,0]"；
  //   G4 由"个股20日收益>上证"→"个股20日收益<上证（深跌）"），preFilter 的 trendOk 与 E2 回踩门在反手态放松。
  // 持有期/止损/止盈/组合层/宇宙全部不变 → 纯净 A/B 对照，直接验证信号方向是否反了。
  invert: boolEnv('CHUANG_INVERT', false),

  // ===== 双创 E1–E3 执行层（默认开启，保留核心逻辑）=====
  execution: {
    enabled: boolEnv('CHUANG_EXEC', true),
    E1_tpR: 2.0, E1_tpAtr: 1.8,               // E1 弹性止盈：TP = max(2.0×SL, 1.8×ATR14)
    E2_pullbackTol: 0.03,                     // E2 回踩入场：信号bar低点回踩至 MA20±3% 内且收在 MA20 上
    E3_trailPct: 0.02,                        // E3 跟踪止损：3% → 2%
    E3_trailTrigger: numEnv('CHUANG_E3_TRIG', 0), // E3 盈利触发门槛：价格先越过 entry*(1+trig) 才开始跟踪（2026-08-17 P0 新增；0=即日跟踪）
    kAtr: 2.5,                                // 双创动态止损倍数（网格可覆盖）
    maxHold: 8,                               // 双创持有期（网格可覆盖）
    tol: 0.03,                                // 开盘偏离容差（双创）
  },

  // ===== 预过滤（trend/vol/gap，主板与双创共用，保留）=====
  preFilter: { maShort: 5, maTrend: 20, volMult: 1.2, gapDown: 0.04, gapUp: 0.06 },

  // ===== 指数 / 市况 =====
  index: { maWin: 60, ma20Win: 20, ma20agoWin: 20 },

  // ===== 否决层（TSQ / PBES，圆桌新增；默认关闭 → 回测 parity 不变）=====
  // 圆桌共识：在负期望池子里第一动作是"少亏"（砍尾部），否决层价值排序高于新主信号。
  // 定位：挂在 G1–G5 + 大盘开关 + E 层之后做尾部剔除（不替代动量，只砍最烂样本）。
  // 数据代理说明：
  //   TSQ 的"换手突增"用成交量比 vol[i]/median(vol[i-19..i]) 代理（kline 无换手率字段，
  //        流通盘稳定假设下等价于换手率比；除权日噪声可接受，因只否极端 TS>6）。
  //   PBES 的"近5年 PE 分位"用价格滚动窗口区间位置近似（fundamental.json 无 PE 历史序列、
  //        pe/pb 多为 null；EPS 斜率用 npGrowth 代理；科创板 npTtm<=0 不否决，因 EPS 斜率无法定义）。
  // enabled=true 时：TSQ 否决 volRatio>6 或连板≥4；PBES 否决 价格分位>0.8 且 npGrowth<=0。
  veto: {
    enabled: boolEnv('CHUANG_VETO', false),
    tsq: {
      enabled: true,
      volRatioMax: 6,        // TS=当日量/20日量中位 > 6 → 极端放量（主力对倒/游资一日游尾声）→ 否决
      limitUpStreakMax: 4,   // 连板 H ≥ 4（涨停高潮随时炸板）→ 否决
    },
    pbes: {
      enabled: true,
      pePctLookback: 250,    // 价格滚动窗口（日），近似"近1年 PE 分位"；数据仅~2.7年，用全历史近似近5年
      pePctMax: 0.80,        // 价格分位 > 0.8（贵）
      epsSlopeMax: 0,        // 且 npGrowth(=EPS斜率代理) ≤ 0（无增长）→ 一票否决
    },
  },

  // ===== 大盘开关（DRFR，圆桌新增；默认关闭 → 回测 parity 不变）=====
  // 圆桌共识：现有价格动量在下跌市持续开火是被磨损的根因，应先加一道市况开关。
  // 开门 = 创业板指 RS(5日)=创业板5日−沪深3005日 > 0 且 站上自身20日线 且 量 > 前20日均
  // 停火 = RS<0 连5日 或 创业板指20日跌幅 < −10%（由 open 的反面近似）
  // enabled=true 时：仅做开门时段（部署态）；enabled=false 时：仍对所有信号打标，bySwitch 给出开门/关门子样本（验证态）
  // 变体（短线冲浪手简化版）：ma20Required=true、rsRequired=false、volRequired=false → 仅"创业板指站上20日线"
  marketSwitch: {
    enabled: boolEnv('CHUANG_SWITCH', false),
    indexFile: 'D:/WorkBuddy/选股结果/switch_index.json',
    rsLookback: 5,        // RS 回望窗口（日）
    maWin: 20,            // 创业板指站上 N 日线
    volMult: 1.0,         // 量 > 前 N 日均量 × volMult 才开门
    rsRequired: true,     // 是否要求 RS>0
    ma20Required: true,   // 是否要求站上20日线
    volRequired: true,    // 是否要求量能放大
  },

  // ===== TLS 板块内龙头主筛（圆桌路线 B；默认关闭 → 回测 parity 不变）=====
  // 圆桌共识（报告 line 142）：把候选池从全宇宙压到「当周主线板块内龙头前N」——
  //   先缩小空间再走 gates/veto，让否决层在龙头样本上真正生效（解决 G3 与 PBES 互斥导致的否决层冗余）。
  // 定位：主筛（最外层过滤，先于 preFilter/gates/veto）；仅双创生效。
  // 数据代理（data_hot/north_hot_plate 已停更 2024-08-16）：
  //   当周主线 = 申万一级行业 近 hotSectorLookback 日等权平均收益 Top hotSectorTopN（从全宇宙 K线自算，保证回测一致）。
  //   R_amt = 当日成交额(=vol*100*close) 板块内百分位(权 wAmt)；R_ret = 近5日收益 板块内百分位(权 wRet)；
  //   R_lead = 当日收益 板块内百分位(权 wLead，龙头当日领涨)。TLS = 加权和，取 TLS≥tlsMin 且成交额前 amtTopN。
  // 注意：universeFile 必须指向与回测引擎一致的 1270 宇宙（universe_klines.json），否则成员资格检查失效。
  tls: {
    enabled: boolEnv('CHUANG_TLS', false),
    universeFile: 'D:/WorkBuddy/选股结果/universe_klines.json',
    sectorFile: 'D:/WorkBuddy/选股结果/universe_sectors.json',
    tlsMin: numEnv('CHUANG_TLS_MIN', 0.90),        // 综合龙头强度阈值（验证期可调低，如 0.80）
    amtTopN: numEnv('CHUANG_TLS_TOPN', 3),         // 每个主线板块内取成交额前 N
    wAmt: 0.40, wRet: 0.35, wLead: 0.25,  // R_amt / R_ret / R_lead 权重
    hotSectorLookback: 5,    // 板块近 N 日收益判定当周主线
    hotSectorTopN: numEnv('CHUANG_TLS_HOTN', 5),   // 取收益前 N 行业为当周主线
    hotSectorMinConstituents: 5,  // 板块当日有≥N 支成分股有 ret5 才参与主线评选（过滤噪声小板块）
  },

  // ===== 组合层风控（保留）=====
  portfolio: { maxBuyPerDay: 3, ddPause: 0.08 },

  // ===== 网格搜索 =====
  grid: {
    mode: env.BT_GRID || 'full',             // full(48) / quick(16) / single
    kList: [1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
    hList: [5, 8, 10, 12],
    rList: ['none', 'not_bear'],
    kSingle: numEnv('BT_K', 3),
    hSingle: numEnv('BT_H', 5),
    rSingle: env.BT_R || 'none',
  },

  // ===== 达标线（用于筛 PASS 配置）=====
  passCriteria: { expMin: 0.30, pfMin: 1.6, kellyPos: true, nMin: 30 },

  // ===== 4.3 全市场优化 =====
  basket: { enabled: env.BT_BASKET === '1' },

  // ===== 新增可配置指标层（C1 质量增长筛选：开 revGrowth/npGrowth，关 pe/pb 待补数据）=====
  // 开启后作为额外筛选门槛，不改变默认回测行为；用于后续新 edge 研究。
  // 注意：fundamental.json 边车当前仅 9 支、无 PE/PB 字段，故 pe/pb 保持关闭（开启会因 null 全剔）。
  extraFilters: {
    pe:         { enabled: false, min: 0,    max: 60 },   // 市盈率（边车暂无字段，保持关）
    pb:         { enabled: false, min: 0,    max: 10 },   // 市净率（边车暂无字段，保持关）
    revGrowth:  { enabled: true, min: 0 },                 // C1: 营收同比增长(%) ≥ 0（剔除下滑）
    npGrowth:   { enabled: true, min: 0 },                 // C1: 净利润同比增长(%) ≥ 0（剔除下滑/亏损）
    macd:       { enabled: false, goldenCross: true },     // MACD 金叉 / 零轴上方
  },

  // ===== 持仓比例建议（signals 输出用）=====
  position: {
    method: 'kelly_atr',    // kelly_atr | fixed | vol_parity
    base: 0.10,             // 单笔基础仓位（fixed 用）
    kellyFraction: 0.5,     // Kelly 安全系数（半仓）
    atrRiskPct: 0.02,       // 单笔最大回撤预算（用于 ATR 仓位）
    maxPosition: 0.20,      // 单标的仓位上限
  },

  // ===== 观察轨道选择器（5.1–5.6，圆桌重构方案；默认 'none'=走原动量范式）=====
  // 仅观察信号、不真实下单；每条轨道的因子来自方案0数据基建（data0 各 store）。
  // 缺数据时对应轨道对该票返回空（优雅降级，不报错）。
  track: { active: env.CHUANG_TRACK || 'none' },   // none|5.1|5.2|5.3|5.4|5.5|5.6

  // ===== 方案0 数据基建产物路径（六轨道共同依赖；缺数据=回测未来函数）=====
  data0: {
    consensusFile:  'D:/WorkBuddy/选股结果/consensus_store.json',   // 机构一致预期(REV_4W/FWD_PEG/FY1 np同比) 周度落库
    fundFlowFile:   'D:/WorkBuddy/选股结果/fundflow_store.json',    // 主力净流入 20日历史序列（1270循环）
    pePctFile:      'D:/WorkBuddy/选股结果/pe_pct_store.json',       // PE_TTM 历史分位(自算代理) + 边车PE
    quarterlyFile:  'D:/WorkBuddy/选股结果/quarterly_store.json',   // 预告/快报/正式 三时点对齐(单季NP同比/环比/毛利环比/现金流质量)
    valuationFile:  'D:/WorkBuddy/选股结果/valuation_store.json',  // 真实估值历史序列(逐日PE_TTM分位/总市值) 1270
    min5File:       'D:/WorkBuddy/选股结果/min5_store.json',        // 5分钟/竞价粒度(样本)
    auditFile:      'D:/WorkBuddy/选股结果/audit_1270.json',        // 1270 字段非空率审计
  },

  // ===== 5.1–5.6 观察轨道阈值（圆桌六方案落地的工程化参数；默认关，仅观察）=====
  tracks: {
    // 5.1 产业策略师：产业景气门控 + 链内卡位轮动（持有 40-60 日）
    '5.1': { enabled: boolEnv('TRACK_51', false), hotSectorTopN: 5, retLook: 20, holdMin: 40, holdMax: 60,
             npGrowthMin: 50, revGrowthMin: 25, ma20ExtMax: 0.12 },
    // 5.2 信号派首席：龙头深坑 + 资金放量表态（深跌≥20% + MainNetFlow≥20日95分位且转正；持 20-60 日）
    '5.2': { enabled: boolEnv('TRACK_52', false), dip20dMin: -0.20, flowPctMin: 0.95, holdMin: 20, holdMax: 60 },
    // 5.3 估值分析师：盈利修正方向 + 前瞻 PEG（REV_4W≥+3%连2期、FWD_PEG∈(0,1.2]、FY1净利同比>20%；月调仓）
    '5.3': { enabled: boolEnv('TRACK_53', false), rev4wMin: 3.0, pegMax: 1.2, fy1NpMin: 20, holdDays: 20 },
    // 5.4 逆向投资人：大市值深跌·支撑位分批承接（回撤≥35%且离底≤25%、pe分位<30%；10份分批无止损、持6-36月→回测用60日代理）
    '5.4': { enabled: boolEnv('TRACK_54', false), drawdownMin: 0.35, nearBottomMax: 0.25, pePctMax: 0.30, holdDays: 60, mcapMin: 5.0e10 },
    // 5.5 财报研究员：季报加速度 PEAD（单季NP同比≥+30%且环比>0、毛利环比≥+1pct、现金流质量≥0.6；T+1~T+3建仓、持45-60日）
    '5.5': { enabled: boolEnv('TRACK_55', false), sqNpYoYMin: 30, sqNpQoQMin: 0, gmQoQMin: 1.0, cfQualityMin: 0.6, holdMin: 45, holdMax: 60 },
    // 5.6 短线冲浪手：MSC 多周期一致性主线 + T+1~T+3（close>MA5>MA20、MACD柱>0、板块5/20日强度>0、资金20日>0且当日>0；持≤3日）
    '5.6': { enabled: boolEnv('TRACK_56', false), holdDays: 3, ma20ExtMin: 0 },
  },
};

// 网格展开：返回配置数组（与旧 grid 构造一致）
function buildGrid(cfg) {
  const g = cfg.grid;
  let kList = g.kList, hList = g.hList, rList = g.rList;
  if (g.mode === 'quick') { kList = [2.5, 3.0, 3.5, 4.0]; hList = [5, 8]; }
  if (g.mode === 'single') { kList = [g.kSingle]; hList = [g.hSingle]; rList = [g.rSingle]; }
  const grid = [];
  kList.forEach(kAtrDyn =>
    ['chuang_only'].forEach(boards =>
      rList.forEach(regime =>
        hList.forEach(maxHoldDyn => {
          grid.push({
            kAtrDyn, boards, regime, maxHoldDyn,
            maxHoldMain: cfg.main.maxHold,
            from: cfg.period.from, to: cfg.period.to,
          });
        }))));
  return grid;
}

module.exports = { CHUANG_CONFIG, boolEnv, numEnv, buildGrid };
