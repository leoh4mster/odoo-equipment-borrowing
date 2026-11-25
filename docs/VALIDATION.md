# 验证记录与复现方法

整理日期：2026-11-25。当前模块版本：`19.0.1.5.0`。

## 1. 当前验证结果

| 项目 | 版本与时间 | 结果及边界 |
| --- | --- | --- |
| 新安装与模块自动化测试 | `19.0.1.5.0`，2026-11-25 | 在全新数据库 `equipment_module_test_b5418cda` 安装模块，44 项测试，0 失败、0 错误 |
| 独立事务并发批准 | `19.0.1.5.0`，2026-11-25 | 两个事务同时批准同设备的不同申请，一条成功，一条被唯一索引拦截；归还后重新批准成功 |
| 中文、英文与界面元数据 | `19.0.1.5.0`，2026-11-25 | 64 条翻译完整；菜单、字段、选项、按钮、搜索条件、空页面提示和“新建”占位显示检查通过 |
| 当前权限与业务错误提示 | `19.0.1.5.0`，2026-11-25 | 独立登录员工和管理员账号，检查待审批入口、员工申请范围及直接调用时的拒绝提示 |
| 三角色完整 HTTP 验收 | `19.0.1.3.0`，2026-11-24 | 当时 39 项检查通过；属于此前版本的阶段记录，不计作当前版本重新运行的 39 项测试 |
| 模块升级与数据保留 | 升级至 `19.0.1.5.0`，2026-11-25 | 比较升级前后的设备、申请及创建/更新时间；当时 3 台设备、8 条申请一致 |

机器可读摘要见 [validation-summary.json](evidence/validation-summary.json)，当前 44 项测试的日志节选见 [module-tests.txt](evidence/module-tests.txt)。并发检查输出中保留的是测试库记录编号，不是开发库业务数据。

### 自动化测试覆盖范围

| 测试文件 | 数量 | 主要内容 |
| --- | --- | --- |
| `test_equipment.py` | 9 | CRUD 权限、必填项、编号唯一性、归档保留与删除限制 |
| `test_borrow_request.py` | 19 | 默认值、自动编号、身份与状态伪造、记录隔离、日期与归档设备、关联列表、复制申请 |
| `test_borrow_workflow.py` | 16 | 完整流程、拒绝分支、非法转换、越权动作、提交后冻结、占用索引和归还释放 |
| 合计 | 44 | 使用 Odoo `TransactionCase`，每项用例在事务测试环境中执行 |

界面检查通过真实认证 HTTP 会话读取 Odoo 返回的菜单、视图和字段元数据，并验证代表性业务错误；它不等同于自动浏览器截图或视觉回归测试。审批流程与待审批高亮已完成本地人工确认，当前源码包未附页面截图。

## 2. 在独立数据库复现 44 项测试

先完成 [安装说明](INSTALL.md)，在同一个终端设置其中的 `PROJECT_DIR`、`ODOO_SOURCE`、`ODOO_PYTHON`。PostgreSQL 角色需要 `CREATEDB`，并预留一个空闲 HTTP 端口；以下示例使用 `8071`。

选择一个尚不存在的独立测试库名称。不要把 `TEST_DB` 设置为正在使用的业务库。

```bash
TEST_DB="equipment_module_test_$(date +%Y%m%d_%H%M%S)"

"$ODOO_PYTHON" "$ODOO_SOURCE/odoo-bin" \
  -c "$PROJECT_DIR/local/odoo-review.conf" -d "$TEST_DB" \
  -i equipment_borrowing --without-demo \
  --test-enable --test-tags /equipment_borrowing \
  --http-interface 127.0.0.1 --http-port 8071 \
  --no-http --stop-after-init --max-cron-threads 0 \
  --logfile "$PROJECT_DIR/local/$TEST_DB.log"
```

测试选择和安装参数采用 Odoo 19 官方 [测试机制](https://www.odoo.com/documentation/19.0/developer/reference/backend/testing.html)。测试模式可能仍启动测试 HTTP 服务，因此单独指定端口，避免影响演示实例。

应在日志结尾看到：

```text
0 failed, 0 error(s) of 44 tests
```

若出现失败，应查看 `FAIL`、`ERROR` 和对应堆栈，不能仅以进程退出或服务器启动成功作为通过依据。本次验收同时核对了进程退出码与测试统计。

## 3. 复现两个独立事务的并发批准

继续使用上一步的 `TEST_DB`，执行：

```bash
"$ODOO_PYTHON" "$ODOO_SOURCE/odoo-bin" shell \
  -c "$PROJECT_DIR/local/odoo-review.conf" -d "$TEST_DB" \
  --no-http --max-cron-threads 0 \
  --logfile "$PROJECT_DIR/local/$TEST_DB-concurrency.log" \
  < "$PROJECT_DIR/scripts/check_concurrent_approval.py"
```

脚本只接受以 `equipment_module_test_` 开头的数据库名称，会创建测试用户、设备和申请并提交事务，以便两个独立数据库连接访问同一批记录。它不会清空数据库；复现时应使用专门的测试库。

检查过程：

1. 两个普通员工分别提交同设备的借用申请。
2. 两个管理员分别在独立事务中确认设备尚未占用。
3. 使用同步屏障让两个事务同时继续批准。
4. 验证结果恰好为一个 `approved`、一个 `blocked_by_unique_index`。
5. 验证数据库中有效占用只有一条。
6. 将成功的申请借出并归还，再批准另一条申请，验证占用释放。

最终 JSON 应包含 `"active_requests_after_race": 1`、`"reapproval_after_return": "passed"` 和 `"result": "passed"`。完整脚本随源码包提供，不依赖当前开发机的绝对路径。

## 4. 尚未覆盖的验证

- 未开展生产环境部署、负载测试、多公司隔离测试或跨 Odoo 主版本兼容性测试。
- 未在 Linux、Windows 上实机验收；安装步骤面向已有 Odoo 19 环境，平台依赖按官方文档准备。
- 未执行模块卸载验收。当前以升级保留数据的方式迭代，未用卸载重装验证已有业务记录。
- 未提供浏览器自动化回归测试或页面截图文件。

本文件区分当前自动化测试、历史角色验收、接口检查与人工确认，不将它们相加为同一种测试数量。
