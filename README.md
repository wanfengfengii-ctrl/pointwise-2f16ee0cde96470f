# 留样复核档案

金属板材来料试验室用留样交接单记录每个测点可能对应的实物原片。交班后源库关闭，夜班需要根据收到的固定件判签，次班质控员需要按原号领取当天报告及首执。

## 一次交班

1. 登记员从量测单登记原片号、整数微米厚度和原单号。同值异片各有身份。完全重放返回原登记，同号修改拒绝。
2. 编录员明确本卷原片范围，为每个测点填写候选。已知没有候选时填写空集合。
3. 编录员提交草稿冻结。缺失原片或越卷引用拒绝冻结。更正另建草稿并按新内容产生卷号，两版均按号可读。
4. 白班为指定冻结卷选择可复核测点并发行固定件。未披露的原名、原单及专用原片身份和厚度留站。固定件携带足够的整卷占用依据。
5. 隔离席按预期件号实收，源库随后可以关闭。原件经完整性、披露名册和正文绑定检查后保存。
6. 夜班从指定实收件后选一个或两个不同的披露测点。复核检查全卷中的实物排他归属，包括未披露义务和与所选点不相连的义务。
7. 所有合法归属给出唯一的所选厚度和时才签存。报告与首执在一个事务中写入。相同规范请求重试返回原成果。
8. 次班质控员重开隔离库，按报告号核对并领取原正文及原首执。新卷及同名测点的后续签发仍可各按原号领取。

## 计算口径

合法归属为全卷每个测点分配一枚候选实物，每枚实物最多分配一次。归属可以有多种，只要所选点厚度和都相同即可签。在样卷中，A 和 B 都可以考虑 7、11、13 μm 的原片。隐藏的 C 必取 13 μm 时，A 和 B 分别待辨，联合只能签 18 μm。更正卷的 C 必取 7 μm 时，联合签 24 μm。两份成果绑定各自的卷、固定件和实收记录。

`no_assignment` 表示整卷无解，`ambiguous` 表示合法归属存在但所选和不同，`signable` 表示所选和唯一。Python 读数和总和均为精确整数。厚度输入拒绝空值、布尔值、浮点数和数字字符串。持久正文用规范十进制文本保存微米值，避免 SQLite 整数范围和 JSON 数值精度限制。测点名、实物号与原单号按原文相等判定。固定件、报告和首执没有依赖时钟的字段。相同输入和正文版本产生确定的身份及规范字节。

## Python 接口

| 入口 | 行为 |
| --- | --- |
| `volumes.store.initialize_source(db)`、`reports.store.initialize_isolated(db)` | 初始化各自的 SQLite 库，可重复运行并保留用户数据 |
| `specimens.register.register(db, specimen_id, micrometers, original_reference)` | 登记并返回 `SpecimenRecord` |
| `specimens.history.get_specimen(db, specimen_id)` | 按原片号读取原量测 |
| `volumes.draft.create_draft(specimen_ids, candidates)`、`volumes.freeze.freeze(db, draft)` | 按测点到候选原片号的映射创建草稿并冻结，返回 `FrozenVolume` |
| `volumes.snapshot.read_frozen_volume(db, volume_id)` | 按冻结卷号读取原快照 |
| `packets.issue.issue(db, volume_id, disclosed_points)` | 返回带 `packet_id` 和 `wire` 的 `FixedEnvelope` |
| `packets.receive.receive(db, expected_packet_id, wire)`、`packets.receive.read_received(db, intake_id)` | 实收并按实收号重读固定件，返回 `ReceivedPacket` |
| `review.adjudicate.review(db, intake_id, points)` | 返回 `ReviewDecision`，其中 `total_um` 只在可签时有值 |
| `reports.sign.sign(db, decision)` | 核对裁决后原子签存，返回 `ReportBundle` |
| `review.workbench.review_and_sign(db, intake_id, points)` | 执行一次夜班操作，返回裁决和可选的成套签报 |
| `reports.history.read_report(db, report_id)` | 获取并对账原定稿、首执、原请求和固定件引用 |

`db` 为调用方打开的 Python 3.11 `sqlite3.Connection`。初始化及写入口在空闲连接上调用，写入口负责各自的提交和回滚。无效输入报 `InputError`，登记冲突报 `ConflictError`，未知冻结卷和报告报 `MissingRecord`，无效来件报 `PacketError`，未知实收件和选点错误在复核入口报 `RequestError`，不合格的签存或提交失败报 `SignError`。档内原定稿与首执不一致时报 `ReconciliationError`。这些业务异常继承 `archive_core.ArchiveError`。

固定件外层为版本 1 的规范 JSON 字节，绑定卷号、披露名册、正文摘要和件号。实收使用操作者提供的预期件号核对来件。`samples/legacy_packet.json` 是可实收和离线复核的完整披露旧件录制，原字节包含读数、实物引用和完整披露声明。

## 运行

使用 Python 3.11 和标准库。控制台物化项目时提供 `check_project.py`。完整正常回归覆盖 V1 至 V9。

```sh
python3 -B check_project.py
```

演示把 `samples/night_shift.json` 装入临时双库，经发行、实收、关闭源库、签存及重开领取，核对原签 18 μm 和更正件签 24 μm。

```sh
python3 -B lab_demo.py
```

V1、V2 核对登记身份、输入有效性和冻结保持。V3、V4 核对定向证据、旧件、错件及实收重放。V5 至 V7 核对指定件、单点双点、无解及精确和。V8 使用 SQLite 延迟外键制造实际提交失败并核对回滚和重试。V9 核对重新初始化、同名选点的后签成果、原号领取和首执一致性。测试与演示仅使用项目样例和临时数据库。
