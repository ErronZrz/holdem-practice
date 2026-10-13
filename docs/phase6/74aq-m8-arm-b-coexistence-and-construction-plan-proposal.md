# 74aq M8：arm_b 并存规则与构造计划载荷提案

> 日期：2026-10-13。
>
> **战役归属**：`74`（「新身份研发与独立验证」战役）。本文件是该战役的第 `44` 份文档，编号 `74aq`。
>
> **历史关系**：承接已生效的 `74r`（`baseline-effective-seed = per-hand-arm_b-material`；构造计划载荷为每座一个 `material`）、已生效的 `74am`（L-3 v2 的六字段 κ）、审查通过的 `74ap`（封闭条目 45 项；L-4 冲突与 `KappaDecisionPlan` 只列了选项）。本文件**不修改** `74r`、`74am`、`74an`、`74ao`、`74ap` 的正文。
>
> **编号范围**：双后缀 `aq`。本文件不预占 `ar` 及之后编号，也不指定将来承载锁定文本的后缀。
>
> **本文性质**：**提案**。写下两项已选定路线的字面写法：L-4 原句保留、另写并存规则；逐 κ 计划并入 `construction-plan-digest` 的载荷形状。**不是**锁定文本；**不是**实现；**不是** K-4 结论；**不是** ③ 重跑。
>
> **首轮审查**：**暂不通过**。阻断是：版本 2 的 `materials` 没有写死来自闭合集切片；`event_index` 没有写明按整数值比较；§6 遗漏 L4-J8、L2-J5 与 G-6；没有说明送交材料载荷不改 `74r` §8.3.10；没有说明版本 2 对象上的 `schema` 与 Q-6 的关系。
>
> **就地修订**：只改本文件。切片改为闭合集在指定位置上的完整切片，分叉后用到集外键即硬失败；排序改为整数值；§6 补上遗漏判据；写明本提案不改 §8.3.10，并把该载荷列入独立 ③；写明 `schema` 只加在版本 2 对象上，版本 1 载荷不加。
>
> **效力限定（写死）**：
>
> - 下文的句子和载荷在未来的锁定文本逐字采用之前**一律无效**。当前身份仍使用待处理字符串，当前构造计划仍是 `74r` 的每座一个 `material`。
> - **不**改 `74r` 的 `per-hand-arm_b-material`。版本 1 继续读这一句。版本 2 要读的那一句只写在本提案里，不写进 `74r`。
> - **不**改代码，**不**替换待处理标记，**不**把 `KappaDecisionPlan` 绑进身份。
> - **不**建立 C-2′，**不**形成 K-4 或 ③ 结论，**不**使 A 路径成立，**不**进入 ④–⑦。
> - **不**生成任何摘要、材料、campaign、seed 或键；**不**创建 `mixed-local@9`。
> - **不**改索引；**不**运行命令；**不**提交或推送。

## 1. 授权原文与范围

用户授权原文要点：

```text
决策 1：L-4 冲突采用「原句保留并另写已裁定的并存规则」。
授权起草 74aq，只做提案，不是锁定文本。内容限于：
并存规则的字面写法，包括版本 1 读 per-hand-arm_b-material、版本 2 读哪一句；
待处理标记被替换成什么值，以及它如何随该规则同步改动；
对 74r L4-J3、L4-J10、固定文本夹具、条目计数的影响清单；
失效传播，以及后续必须独立③重验的范围。

决策 2：KappaDecisionPlan 并入现有构造计划摘要。
同在 74aq 里只做载荷形状设计，不写代码。内容限于：
版本 1、版本 2 各自的构造计划载荷；
逐 κ 项的排序、字段和整数 seed 范围；
与 construction-plan-digest 的绑定方式，以及版本 1 的缺席取值；
对现有夹具和 baseline-effective-samples、baseline-effective-bluff-freq 的影响。

禁止：修改 74r、74am、74an、74ao、74ap 或 L-4 取值；
写代码绑定 KappaDecisionPlan 或替换待处理标记；
生成实际材料、campaign、摘要、seed 或键；
推送以及新的提交；形成 K-4、C-2′ 或③结论；进入④–⑦。
```

**属于本文件**：并存规则的提案句子、待处理标记的提案替换值、判据与夹具影响、失效与③范围、两套构造计划载荷的提案形状。

**不属于本文件**：锁定正文；代码；索引；K-4 是否升参考版本或评估版本。

## 2. 文件级改动与执行类别

| 文件 | 改动 |
|---|---|
| `docs/phase6/74aq-m8-arm-b-coexistence-and-construction-plan-proposal.md` | **新增**后经审查 **就地修订**（闭合集切片、整数排序、遗漏判据、送交材料载荷与 `schema`） |

| 类别 | 内容 |
|---|---|
| 锁定提案 | 并存规则的字面写法；两套构造计划载荷的形状 |
| **未执行** | 锁定、改既有文档、改代码、替换待处理标记、索引、命令、摘要／材料／campaign／seed／键、K-4 结论、C-2′、③ 重跑、④–⑦、提交、推送 |

## 3. 已选定且本提案不再打开的路线

| 项 | 选定 |
|---|---|
| L-4 冲突 | 原句保留，另写并存规则。不改 `per-hand-arm_b-material`，也不把来源句改成只剩逐 κ |
| 逐 κ 计划 | 并入现有条目 `construction-plan-digest`。不新增身份条目，也不只留在包外 |

参考版本或评估版本是否因此升版，本提案**不回答**。

## 4. 并存规则的提案字面

下列句子是提案。锁定文本采用之前，执行身份不得改读它们。

```text
baseline-effective-seed 按协议 schema 只读一句，两句不得互换。

randomization-protocol-v1：
该条目逐字等于 per-hand-arm_b-material。
这句只属于版本 1。被测基线座位的 seed 来自每手一条 arm_b 材料，
键是 (campaign, block, hand)。这句不承载整数。
版本 1 不得改读 per-kappa-arm_b-material。
六字段键不得充当版本 1 的 arm_b 来源。

randomization-protocol-v2：
该条目逐字等于 per-kappa-arm_b-material。
这句只属于版本 2。被测基线座位的 seed 来自 arm_b 材料，
键是 (campaign, block, hand, seat, event_index, sigma_public)。
同一手可以有多条，以 event_index 区分。这句不承载整数。
版本 2 不得改读 per-hand-arm_b-material。
手级 arm_b 键不得充当版本 2 的 arm_b 来源。
```

`per-hand-arm_b-material` 仍只写在 `74r` 里，本提案不改那一处。`per-kappa-arm_b-material` 是提案中的新固定文本，字符都在可见 ASCII 内，不含空格。它在锁定文本采用之前不是身份的合法取值。

两条来源句都只说明材料从哪一类键来。整数 seed 仍不写进这两句，仍由 §7 的构造计划载荷承载。

## 5. 待处理标记的提案替换值

条目名 `arm-b-seed-scope-conflict` 保留。它仍排在 `baseline-effective-seed` 之后、`baseline-effective-samples` 之前。封闭集合因此仍是 45 项，`instantiation-caliber` 仍是 17 项。

| 时机 | 取值 |
|---|---|
| **现在，以及本提案未被锁定采用之前** | `pending:per-hand-arm_b-material-vs-per-kappa-arm_b` |
| **将来的锁定文本采用 §4 的同一天，同一次改动** | `settled:v1-per-hand-arm_b-material/v2-per-kappa-arm_b-material` |

替换值也是可见 ASCII，不含空格。版本 1 和版本 2 的身份都写这同一个替换值。它记录「两句已经按 schema 分开」，不代替 `baseline-effective-seed` 里那句来源文本。

同步义务：锁定文本若采用 §4，必须在同一次采用里把上表第二行写成该条目的固定值。只改来源句、留下待处理字符串，或者只改标记、不写明版本 2 读哪一句，都不算采用。本提案本身不执行这次替换。

## 6. 对判据、夹具和条目计数的影响

这些影响在锁定文本采用并随后实现时发生。本提案不改判据正文，也不改夹具。

| 对象 | 影响 |
|---|---|
| **L4-J3** | 今天把 `baseline-effective-seed` 当成一句固定文本。采用后，版本 1 仍逐字等于 `per-hand-arm_b-material`；版本 2 逐字等于 `per-kappa-arm_b-material`。用一句覆盖两种 schema 的旧预期，对版本 2 记录失效。`arm-b-seed-scope-conflict` 的合法渲染从待处理字符串改为 §5 的替换值，两种 schema 相同 |
| **L4-J10** | 前半句「固定文本是 `per-hand-arm_b-material`」改为按 §4 分 schema。后半句的整数范围不放宽：版本 1 每个 `material.value`、版本 2 每条 κ 的 `value`，仍是 `[0, 2^256)` 内的整数。空值、布尔和非整数仍失败 |
| **L4-J8** | 该判据要求 `construction-plan-digest` 按 `74r` §8.3.9 重算。版本 1 仍按该节。版本 2 改为按 §7.2 重算，因此「版本 2 记录也只按 §8.3.9 重算」的旧预期失效 |
| **L2-J5** | 上界仍是 `[0, 2^256)`，不放宽。版本 1 仍检查每个基线与非被测座位的 seed。版本 2 改为检查该座位切片里的每一条 κ 的 `value`，不是只检查一个 `material.value` |
| **G-6** | 与 L2-J5、L4-J10 同一范围：身份接口层和构造计划里的每一个基线或非被测 seed 仍须落在 `[0, 2^256)`，基线 seed 不得为空。版本 2 把「每一个」读成切片中的每一条，不把多条 κ 合成一个上界 |
| **固定文本夹具** | 凡断言待处理字符串的夹具，在实现授权改标记时必须改断言。版本 1 夹具的 `baseline-effective-seed` 仍是原句。版本 2 夹具必须断言 `per-kappa-arm_b-material`，不能再断言原句 |
| **条目计数** | 不增不减。六类仍是 `17 + 3 + 13 + 2 + 6 + 4 = 45`。`74r` 里的 16 项与 41 项句子不改；45 项的承接仍是 `74ap`。本提案不新增条目名 |

`baseline-effective-samples` 仍是十进制 `500`。`baseline-effective-bluff-freq` 仍是固定文本 `0.1`。这两条不因并存规则改值，也不进入 §7 的逐 κ 项。

## 7. 构造计划载荷的提案形状

两套载荷是两个摘要对象。版本 1 的字节形状保持 `74r` §8.3.9，本提案不往里面加字段。版本 2 使用另一套形状。因此同一批整数不会因为套错形状而得到同一个 `construction-plan-digest`。

本提案不计算任何一个摘要，也不写下任何一条实际键或实际 seed。尖括号是形状里的占位，不是取值。

### 7.1 版本 1

协议 schema 为 `randomization-protocol-v1` 时，载荷仍是 `74r` §8.3.9 的 JSON 数组：每手每臂一项，`seats` 按座位号升序，每座恰一项，该项含单个字段 `material`。`arm_b` 与 `non_probed` 都是每座一条。没有 κ 列表，也没有「κ 缺席」这种哨兵字符串。

版本 1 的缺席取值就是这套形状本身：座位项里有 `material`，没有 `materials`。不得用一条空的版本 2 列表冒充版本 1。

### 7.2 版本 2

协议 schema 为 `randomization-protocol-v2` 时，载荷是下面这个对象，而不是 §7.1 的数组：

```json
{
  "schema": "construction-plan-v2",
  "hands": [
    {
      "hand_ordinal": "<positive-int>",
      "button": "<non-negative-int>",
      "probed_seat": "<non-negative-int>",
      "arm": "<under-test | baseline>",
      "summary_seats": ["<int>"],
      "summary_scope": ["<int>"],
      "probed_seat_style": "<tight | null>",
      "seats": [
        {
          "seat": "<non-negative-int>",
          "role": "<non-probed | probed-under-test | probed-baseline>",
          "identifier": "<heuristic@1 | mixed-local@9>",
          "interface": "<registry-seed | material-key>",
          "requires_public_summary": "<false | true>",
          "seat_scope": "<null | probed-seat-only>",
          "materials": [
            {
              "purpose_label": "<arm_m | arm_b | non_probed>",
              "index_key": ["<...>"],
              "value": "<non-negative-int>"
            }
          ]
        }
      ]
    }
  ]
}
```

对象顶上的 `schema` 只出现在这套版本 2 载荷里。`74r` 的 Q-6 确认的是当时那两个载荷不增加 `schema`：入口代码载荷（§8.3.8）和版本 1 的构造计划数组（§8.3.9）。本提案不改那两个载荷，版本 1 数组仍然没有 `schema`。版本 2 另成一个对象并写上 `construction-plan-v2`，是为了让两种形状在摘要上不能互换：把版本 2 对象交给版本 1 的重算，或把版本 1 数组交给版本 2 的重算，都对不上。这不把 Q-6 读成「以后任何载荷都不得出现 `schema`」。

手与臂的次序、座位号升序、两侧角色和接口，与 `74r` §8.3.9 相同。变的是材料字段：版本 2 的座位项只有 `materials` 数组，没有单个 `material`。

`materials` 不是该臂在对局里实际走到的决策，也不是分叉之后新出现的公开投影。它是闭合集上的完整切片，再配上已提交材料里同一键的整数。规格、闭合集和材料三者足以重算，不读取对局过程。

| 座位 | 切片 |
|---|---|
| 被测臂的被测座位 | 闭合集里该 `hand` 的全部 `arm_m`。版本 2 的这条键没有 `seat`，所以切片位置是 `(hand, 用途)`，长度恰为 1，键仍是 `(campaign, block, hand)` |
| 基线臂的被测座位 | 闭合集在该 `(hand, seat, arm_b)` 上的全部键。`seat` 必须是该手被测座位。长度至少为 1，每条都是六字段 κ |
| 两臂的非被测座位 | 闭合集在该 `(hand, seat, non_probed)` 上的全部键。长度至少为 1，每条都是六字段 κ |

两臂的非被测座位取同一切片：同一组键、同一个整数。共享规则是 `74am` §7，即同一完整 κ 一条整数、两臂同键同值。版本 2 不按 `74r` §8.3.9 所引的 K-2′ 来解释这组切片。被测座位不共享：基线臂只取 `arm_b` 切片，被测臂只取 `arm_m` 切片。

切片必须恰好等于闭合集在该位置上的键，不少也不多。每一项的 `value` 是已提交材料里同一键的整数。对得上的键缺材料，或材料里多出切片没有的键，重算失败。

分叉之后若要消耗切片以外的键，即为协议失败：停止，不补读、不补键。这与 `74ao` 的缺键硬失败相同。编排器是否真能覆盖两臂各自的投影，留在 K-4 复审核对。本提案不把「已经覆盖」写成事实。

当前实现仍要求每手恰好一条 `arm_b`。那不是本提案的粒度。提案允许同一手有多条 κ，条数等于闭合集在该切片上的条数。将来的实现授权不得把「每手恰好一条」写成这套载荷的规则。

### 7.3 逐 κ 项的排序、字段和整数范围

同一座位内的 κ 数组按 `event_index` 的**整数值**升序，不按 `index_key` 里的字符串字典序。因此 `"2"` 在 `"10"` 之前。整数的解析与键上其他整数字段相同：无前导零的十进制，`0` 写作 `"0"`。平局时再按 `sigma_public` 的字符串升序。`74am` 规定同一 `(seat, event_index)` 至多一条 `sigma_public`，所以在已经合法的闭合集上，这条字符串次序不会改变顺序。它仍写在规则里，避免两个不同投影共用一个序号时排序没有定义。`campaign`、`block`、`hand`、`seat` 在该座位内已经相同，不另排。`arm_m` 那一条只有一个元素，不再排序。

每一项只有三个字段：

| 字段 | 规则 |
|---|---|
| `purpose_label` | `arm_b` 或 `non_probed`。`arm_m` 只用在被测臂被测座位的那一条上 |
| `index_key` | 字符串数组，次序与该用途的键字段次序相同 |
| `value` | JSON 整数，满足 `0 ≤ value < 2^256`。布尔、空值、非整数失败。基线 seed 不得为空 |

`samples` 与 `bluff_freq` 不是这三项的字段。`KappaDecisionPlan` 可以继续在内存里描述一次决策，但摘要只覆盖上表这三个字段，不把该结构的类默认值再抄进载荷。

### 7.4 送交材料载荷

本提案**不改** `74r` §8.3.10。该节 `index_key` 注释里的键形仍是版本 1。版本 2 的 `supplied-materials-digest` 是继续沿用该载荷、只把键换成六字段，还是另有形状，本提案不裁定。独立 ③ 必须把这一点列为覆盖项，不能从本提案推出已经改定。

## 8. 与 `construction-plan-digest` 的绑定

条目名不变，仍是 `construction-plan-digest`。不新增身份条目。

重算规则：

- schema 为版本 1 时，对 §7.1 的数组取 SHA-256。
- schema 为版本 2 时，对 §7.2 的对象取 SHA-256。
- 编码仍是紧凑 JSON、键排序、`ensure_ascii = true`、UTF-8、小写十六进制。本提案不产出任何一个十六进制。

版本 1 的身份若带上 §7.2 的对象，或版本 2 的身份若带上 §7.1 的数组，摘要比对失败。版本 1 没有单独的「κ 缺席」摘要；缺席就是 §7.1 那种不含 `materials` 的形状。

## 9. 对现有夹具和两个基线条目的影响

| 夹具 | 影响 |
|---|---|
| 版本 1 的构造计划夹具 | 载荷形状不变，因此同一批非实际材料的 `construction-plan-digest` 不变。身份摘要仍会变，因为 `arm-b-seed-scope-conflict` 的取值要换成 §5 |
| 版本 2 的构造计划夹具 | 必须改用 §7.2。`construction-plan-digest` 与按 §7.1 算出的值不同。来源句改为 `per-kappa-arm_b-material`，冲突标记改为 §5 |
| `baseline-effective-samples` | 期望文本仍是 `500`。不按 κ 复制 |
| `baseline-effective-bluff-freq` | 期望文本仍是 `0.1`。不接受 `0.10`。不按 κ 复制 |

这两条的期望值不变，不表示整份执行身份的摘要不变。身份摘要会随来源句、冲突标记和版本 2 的计划载荷改变。

## 10. 失效传播与独立 ③ 的范围

本提案不使任何 ③ 结论失效，因为它还不是锁定文本，也还没有改实现。`74af` 的 ③ 总体不通过保持原样。

将来的锁定文本一旦采用本提案，并且实现授权改了身份取值或计划载荷，则下列旧机械预期失效，必须由另一次独立 ③ 重验，不能由本提案代替：

- L4-J3 中「`baseline-effective-seed` 永远是 `per-hand-arm_b-material`」；
- L4-J8 中「`construction-plan-digest` 一律按 `74r` §8.3.9 重算」用于版本 2 记录的预期；
- L4-J10 中同一句固定文本，以及「每座恰好一个 `material.value`」；
- L2-J5 与 G-6 中「每个 `material.value`」若被读成版本 2 仍只有一个值；上界本身不失效，仍是 `[0, 2^256)`；
- 断言待处理字符串的固定文本夹具。

那次独立 ③ 至少要看到：

- 版本 1 身份的来源句仍是 `per-hand-arm_b-material`，计划载荷仍是 §7.1，六字段 `arm_b` 不能通过；
- 版本 2 身份的来源句是 `per-kappa-arm_b-material`，手级 `arm_b` 不能通过；
- 两种身份的 `arm-b-seed-scope-conflict` 都是 §5 的替换值，不再是待处理字符串；
- 版本 2 的 `construction-plan-digest` 按 §7.2 重算，与版本 1 的数组摘要不同；
- 版本 2 座位项的 `materials` 等于闭合集在该 `(hand, seat, 用途)` 上的完整切片；`arm_m` 的切片位置是 `(hand, 用途)`；两臂的非被测座位是同一切片；切片以外的键导致失败且没有补读；
- 每条 κ 的 `value` 落在 `[0, 2^256)`，空值与布尔失败；`event_index` 按整数值排序；
- `baseline-effective-samples` 仍是 `500`，`baseline-effective-bluff-freq` 仍是 `0.1`；
- 版本 2 的 `supplied-materials-digest` 是否仍用 `74r` §8.3.10、只更换键形，还是另有形状；本提案不改该节，重验不能把它当成已经改定；
- 签署人不是本战役的推导方。

C-2′、K-4、A 路径和 ④–⑦ 不在这次重验的通过范围里。即使重验覆盖了上面几条，也不自动构成那些结论。

## 11. 明确不主张

- 本文件不是锁定文本。§4 的句子和 §5 的替换值现在都不是合法身份取值。
- K-4 **未裁定**。本文件不决定参考版本或评估版本是否升版。
- 不建立 C-2′。`74af` 的 ③ 总体不通过持续有效。
- A 路径**未成立**。④–⑦ **均未发生**。
- 不生成摘要、材料、campaign、seed 或键。`mixed-local@9` **未**创建。

## 12. 申请 `74aq` 内容审查

请审查方核验：

1. §4 是否写明版本 1 只读 `per-hand-arm_b-material`、版本 2 只读 `per-kappa-arm_b-material`，并且两句不能互换；
2. §5 的替换值是否与 §4 同一次采用，条目名和 45 项计数是否不变；
3. §6 是否列出 L4-J3、L4-J8、L4-J10、L2-J5、G-6、固定文本夹具和条目计数，并且整数上界没有放宽；
4. §7.2 是否写死 `materials` 是闭合集切片、两臂非被测座位按 `74am` §7 取同一切片，以及集外键硬失败且不补读；版本 1 是否仍是每座一个 `material`，缺席是否是形状本身而不是空列表；
5. §7.3 是否写明 `event_index` 按整数值升序，并注明 `sigma_public` 的字符串次序在「每序号至多一条」下不改变顺序；
6. §7.4 是否写明本提案不改 `74r` §8.3.10，且独立 ③ 必须覆盖版本 2 送交材料载荷；
7. §7.2 是否写明 `schema` 只加在版本 2 对象上，版本 1 载荷不加，从而不把 Q-6 读成禁止以后出现 `schema`；
8. `baseline-effective-samples` 与 `baseline-effective-bluff-freq` 是否仍是 `500` 和 `0.1`，且没有进入逐 κ 项；
9. 是否没有改 `74r`、`74am`、`74an`、`74ao`、`74ap`，也没有生成摘要、材料、seed 或键。
