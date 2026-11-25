# 安装与运行

模块版本：`19.0.1.5.0`。目标环境：Odoo 19 Community。

## 1. 当前开发机：继续使用现有环境

在当前项目根目录执行：

```bash
./dev.sh status
./dev.sh start
```

打开 [本地登录页](http://127.0.0.1:8069/web/login?db=equipment_dev)。系统管理员登录信息保存在 `local/access.txt`，演示账号保存在 `local/demo-accounts.txt`。这些文件只在当前开发机存在，不进入源码包。

| 命令 | 用途 |
| --- | --- |
| `./dev.sh status` | 检查 Python、PostgreSQL、Odoo 和登录页状态 |
| `./dev.sh start` | 启动本项目的 PostgreSQL 和 Odoo |
| `./dev.sh stop` | 停止本项目的进程，保留数据库文件 |
| `./dev.sh restart` | 重启本项目的 PostgreSQL 和 Odoo |
| `./dev.sh upgrade` | 保持 PostgreSQL 运行，停止 Odoo，升级自定义模块，再启动 Odoo |

修改字段、XML、权限或翻译后使用 `upgrade`；仅修改 Python 方法也需要重启 Odoo 以加载新代码。升级后刷新浏览器。

`dev.sh` 使用 `../../work/odoo19-env/` 中的虚拟环境、Odoo 源码和专用数据库集群，以及 `local/odoo.conf`。它依赖本次开发工作区布局；复制本仓库到其他机器后，请采用下面的标准安装方式。

## 2. 其他机器：安装到 Odoo 19

### 2.1 准备 Odoo 与数据库

先按照 [Odoo 19 官方源码安装文档](https://www.odoo.com/documentation/19.0/administration/on_premise/source.html) 准备 Odoo 及其系统、Python 依赖。Odoo 19 要求 Python 3.10 或以上、PostgreSQL 13 或以上；本项目实测版本为 Python 3.12.14、PostgreSQL 16.15。

本模块的 manifest 只依赖 `base`，不需要安装 Enterprise 或付费模块。`requirements-macos-py312.lock.txt` 是本次 Mac 的完整依赖快照，不能替代不同平台上的 Odoo 官方 `requirements.txt`。

Odoo 源码可使用以下固定版本，以对齐本次验证：

```text
https://codeload.github.com/odoo/odoo/tar.gz/4ff91465babd9f88620d78d9db34c75b71fc0006
SHA-256: 17c9edc827f04a5e4dc3aab51a49d7b713806bee487a85cee9d5722668ca402b
```

准备一个能通过 TCP 登录 PostgreSQL 的专用角色。若已有可用的非超级用户角色，可直接使用；否则由 PostgreSQL 管理员创建，例如：

```bash
createuser --host=127.0.0.1 --port=5432 --username=PG_ADMIN_LOGIN \
  --pwprompt --createdb --no-superuser --no-createrole equipment_review_role
```

把 `PG_ADMIN_LOGIN` 改成实际的 PostgreSQL 管理账号。`--pwprompt` 会要求输入新角色的密码；配置 Odoo 时使用相同密码。`CREATEDB` 用于创建演示和测试数据库。

### 2.2 放置模块并填写配置

取得本仓库或解压源码包。`addons_path` 应填写包含 `equipment_borrowing` 的 **父目录 `addons`**。

下面的三个路径变量需要替换为自己的绝对路径；`ODOO_PYTHON` 应指向已安装 Odoo 依赖的 Python：

```bash
PROJECT_DIR="/ABSOLUTE_PATH/equipment-borrowing"
ODOO_SOURCE="/ABSOLUTE_PATH/odoo"
ODOO_PYTHON="/ABSOLUTE_PATH/odoo/.venv/bin/python"
```

确认这是新配置文件，再复制模板：

```bash
mkdir -p "$PROJECT_DIR/local/odoo-review-data"
cp -n "$PROJECT_DIR/config/odoo.conf.example" "$PROJECT_DIR/local/odoo-review.conf"
chmod 600 "$PROJECT_DIR/local/odoo-review.conf"
```

编辑 `local/odoo-review.conf`，填写：

- 所有 `/ABSOLUTE_PATH` 路径：Odoo 的两个官方 addons 路径、本仓库的 `addons`、数据目录及日志路径。
- `db_user`、`db_password`：PostgreSQL 角色与密码。
- `admin_passwd`：自行设置的数据库管理主密码。它与 Odoo 网页用户密码、PostgreSQL 角色密码是三种不同用途的密码。
- 端口：模板使用本机 `8070`，便于与当前开发实例 `8069` 区分。

配置中的密码值保持原样填写，不要额外添加引号。

### 2.3 创建演示数据库

启动 Odoo：

```bash
"$ODOO_PYTHON" "$ODOO_SOURCE/odoo-bin" -c "$PROJECT_DIR/local/odoo-review.conf"
```

打开 [数据库管理页](http://127.0.0.1:8070/web/database/manager)，选择创建数据库，填写：

| 项目 | 填写方式 |
| --- | --- |
| 主密码 | 配置中的 `admin_passwd` |
| 数据库名 | `equipment_review`，与 `dbfilter` 一致 |
| 管理员登录名与密码 | 自行设置并保存在本机 |
| 语言 | 简体中文 / Chinese (Simplified) |
| 演示数据 | 不勾选 |

如果已有同名数据库，改用一个新名字，并同步修改 `dbfilter`。不要删除已有数据库来重复本步骤。

### 2.4 安装模块

两种方法任选一种。

**通过应用页面安装：** 使用系统管理员登录，打开开发者模式（在网址加入 `?debug=1`），进入“应用”，更新应用列表，搜索 `Equipment Borrowing` 或 `equipment_borrowing` 并安装。安装后重新加载页面，进入“设备借用管理”。

**通过命令行安装：** 先在启动 Odoo 的终端按 `Ctrl+C` 停止该审核实例，然后执行：

```bash
"$ODOO_PYTHON" "$ODOO_SOURCE/odoo-bin" \
  -c "$PROJECT_DIR/local/odoo-review.conf" -d equipment_review \
  -i equipment_borrowing --without-demo --no-http --stop-after-init

"$ODOO_PYTHON" "$ODOO_SOURCE/odoo-bin" \
  -c "$PROJECT_DIR/local/odoo-review.conf" -d equipment_review
```

`-i` 安装模块，`-d` 选择数据库，`--stop-after-init` 在初始化完成后退出。命令行安装方式与 Odoo 官方 [开发环境指南](https://www.odoo.com/documentation/19.0/developer/tutorials/setup_guide.html) 一致。

首次数据库创建完成后，可将配置中的 `list_db` 改为 `False`，再重启此实例；登录时使用 `/web/login?db=equipment_review`。模块不会自动创建业务账号或设备，按 [使用说明](USAGE.md) 配置角色并录入设备。

### 2.5 升级模块

保留数据库，停止该 Odoo 实例后执行：

```bash
"$ODOO_PYTHON" "$ODOO_SOURCE/odoo-bin" \
  -c "$PROJECT_DIR/local/odoo-review.conf" -d equipment_review \
  -u equipment_borrowing --no-http --stop-after-init
```

完成后用前面的启动命令恢复服务。`-u` 更新已安装模块；不要用卸载重装代替日常升级。

## 3. 中文界面与角色

数据库应安装简体中文语言，用户个人偏好中的语言设为简体中文。对已有英文数据库，可由系统管理员在设置中安装简体中文，再升级本模块。

- 普通员工：用户类型为“内部用户”，不授予设备管理员权限。
- 设备管理员：内部用户，并授予“设备借用管理 / 设备管理员”权限。
- 系统管理员：用于安装模块与配置账号。模块安装时会把默认系统管理员加入设备管理员组。

新建的设备管理员无需拥有系统设置权限。用员工账号测试时不要切换成超级用户模式，否则无法体现实际权限限制。

## 4. 常见问题

| 现象 | 检查方法 |
| --- | --- |
| 应用中搜不到模块 | 检查 `addons_path` 是否指向父目录、是否重启并更新应用列表 |
| 模块名称搜索不到 | 尝试英文名称或技术名 `equipment_borrowing` |
| 中文仍未显示 | 检查用户语言、数据库是否安装简体中文，升级模块后刷新 |
| 员工没有“待审批”菜单 | 这是角色设计；该入口仅设备管理员可见 |
| 设备列表没有“新建” | 检查当前账号是否为设备管理员 |
| 待审批页面没有“新建” | 该页面用于处理已提交申请；创建申请请进入“借用申请” |
| 批准时报设备被占用 | 检查同设备是否有已批准或已借出的申请，完成归还后再批准 |
| 提交后不能改内容 | 申请提交后会冻结内容，这是服务端业务规则 |
| 本地无法登录 | 先检查 `./dev.sh status`，再查看运行日志；密码在本机 `local/` 中 |

当前工作区日志位于 `../../work/odoo19-env/logs/`。按模板安装的新审核实例日志位于 `local/odoo-review.log`。数据库初始化和依赖编译的具体平台差异，以 Odoo 19 官方安装文档为准。
