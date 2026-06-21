# Catalyst — Demo Walkthrough Script

A talking script for a screen-recording or live interview. Click cues are in
`[brackets]`. The full walkthrough is ~90 seconds; a 30-second version and a
Chinese version follow. Personal aid — keep it out of the repo if you prefer
(add `DEMO_SCRIPT.md` to `.gitignore`).

> Before recording: run `seed_demo`, start the server, full-screen the browser,
> hide the bookmarks bar. Open on the **Home** page.

---

## 90-second version (English)

**[Home page]**
> "This is **Catalyst** — a demo of an inventory-intelligence platform I built for a
> perishable-goods catalog: about 1,200 SKUs that age, sell at very different speeds,
> and get priced, listed, and cleared automatically. It's one site with four apps —
> each one a piece I actually built — so let me walk through them."

**[Click DX Analytics]**
> "Start with the core engine — the production version. Every day it ranks the whole
> catalog on a blend of demand, sell-through, and margin, then sorts every SKU into
> one of eight categories — from high-demand rare items down to liquidate and dispose
> candidates. This power-law curve *is* the catalog: a handful of SKUs carry it, and
> there's a long tail to clear out."

**[Click Catalog, then click into one SKU]**
> "Here's every SKU with its rank, category, velocity, and discount — filterable. Open
> any one and you get the full metrics *plus a plain-English reason* for its category.
> This is what replaced manual triage across thousands of SKUs."

**[Click Analytics]**
> "Now the part I'm most proud of. This is the *first* version I built — textbook
> inventory theory: normalize sales, profit and ROI, find the Pareto-optimal frontier.
> Clean math — but it reads demand off the *current* stock level. Look at these three
> SKUs where v1 and v2 disagree."

**[Point at DEMO-PHANTOM in the comparison]**
> "This one is out of stock with a little stale history. v1 divides by near-zero stock,
> its sell-through explodes, and it ranks it as a star to reorder — which is wrong. The
> v2 engine grounds sell-through in *average* inventory and correctly freezes it. Hitting
> that wall on real data is exactly why I rewrote it as v2."

**[Click Automation]**
> "Listing every variant by hand doesn't scale, so I automated it. **One click** runs the
> whole catalog: each base SKU explodes into eight marketplace listings — variant type by
> pack size — each with a generated SKU and title, posted in bulk batch jobs. The flow view
> shows how the steps connect; you can drill into any job to see each listing's status and
> why a failure happened."

**[Click Lifecycle, then Clearance Queue; point at DEMO-DOOMED]**
> "Finally, lifecycle. Each SKU runs through a six-tier state machine, and aging stock
> gets a clearance discount weighted by rank, shelf age, and overstock. This one — 60-odd
> units barely selling, near the end of its shelf life — gets marked down 38%. A *healthy*
> SKU the same age stays at full price: age alone isn't the trigger, demand-versus-deadline is."

**[Back to Home]**
> "So — ranking and categorization, a real v1-to-v2 redesign, automated listing, and
> lifecycle pricing — all over synthetic data, and fully runnable. Happy to go deeper on
> any piece."

---

## 30-second version (English)

> "Catalyst is an inventory-intelligence platform I built — one site, four apps. **DX
> Analytics** ranks ~1,200 SKUs daily and sorts them into eight categories. **Analytics**
> is my original Pareto-based design — I keep it to show *why* I rewrote it: it misjudges
> out-of-stock items, which the v2 fixes by grounding sell-through in average inventory.
> **Automation** processes the whole catalog in **one click** — fanning each product into
> eight marketplace listings and posting them in tracked batch jobs. **Lifecycle** runs a six-tier state machine with a multi-factor
> clearance discount. All synthetic data, fully runnable — want me to dig into one?"

---

## 90秒中文版

**[Home 首页]**
> "这是 **Catalyst**——我做的一套库存智能平台 demo，面向易过期商品目录：大约 1,200 个 SKU，
> 会老化、销售速度差异很大，并且自动定价、自动上架、自动清仓。一个网站、四个 app，每一个
> 都是我实际做的，我一个个过一遍。"

**[点 DX Analytics]**
> "先看核心引擎——生产版本。它每天用「需求 × sell-through × 毛利」给整个目录排名，再把每个
> SKU 分到八个类别里——从高需求稀缺品，一直到清仓和处置候选。这条幂律曲线就是目录的真相:
> 少数 SKU 撑起整个盘子，长尾是要清掉的。"

**[点 Catalog，再点进一个 SKU]**
> "这里是每个 SKU 的排名、类别、动销、折扣，可筛选。点进任意一个,能看到全部指标,还有一句
> 「为什么是这个类别」的解释。这套东西取代了几千个 SKU 的人工分拣。"

**[点 Analytics]**
> "接下来是我最想讲的部分。这是我做的**第一版**——经典库存理论:把销量、利润、ROI 归一化,
> 找 Pareto 最优前沿。数学很漂亮——但它是按**当前**库存读需求的。看这三个 v1 和 v2 结论不
> 一样的 SKU。"

**[指向 DEMO-PHANTOM]**
> "这个缺货、只有一点旧的销售记录。v1 除以接近零的库存,sell-through 爆表,把它排成要补货的
> 明星品——这是错的。v2 用**平均**库存来算,正确地把它冻结了。在真实数据上撞到这个坑,正是
> 我重写出 v2 的原因。"

**[点 Automation]**
> "逐个变体手工上架没法规模化,所以我把它自动化了。**一键**跑完整个目录:每个基础 SKU 炸开成
> 八条电商 listing——变体类型 × 规格,每条自动生成 SKU 和标题,用批量任务发布。流程图展示各步骤
> 怎么串起来,还能点进任意任务看每条 listing 的状态和失败原因。"

**[点 Lifecycle → Clearance Queue,指向 DEMO-DOOMED]**
> "最后是生命周期。每个 SKU 走一个六层状态机,老化库存按「排名 + 货架年龄 + 积压」加权算清仓
> 折扣。这个——六十多件几乎不动、接近过保——被打 38% 折。一个同样年龄但**健康**的 SKU 仍是
> 原价:触发清仓的不是年龄本身,而是「需求 vs 截止期」。"

**[回到 Home]**
> "所以:排名分类、一次真实的 v1 到 v2 重构、自动上架、生命周期定价——全部基于合成数据,且
> 可以直接跑起来。任何一块都可以深入聊。"

---

## Delivery tips

- **Pace for the camera:** ~140 words/minute. Pause a beat after each `[click]` so the
  page renders before you talk.
- **Lead with "I built / I designed / I rewrote"** — first person, past tense; it's your work.
- **The Analytics (v1) screen is the money shot.** Slow down there — the v1→v2 story is the
  senior signal most candidates can't tell. Let the DEMO-PHANTOM example land.
- **Don't claim live business metrics** (revenue/savings). Say "designed/built", and that
  it's synthetic data — it keeps you bulletproof if they probe.
- **If they interrupt with a question, stop and answer** — an interactive demo beats a monologue.
- **Have one number ready per app**: ~1,200 SKUs · 8 categories · 8 variants/product · 6 tiers.
