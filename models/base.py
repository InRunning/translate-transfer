from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import quote_plus

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

def _load_local_yaml(path: str = "local.yaml") -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data or {}
    except FileNotFoundError:
        return {}


def _to_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _build_database_url(db_cfg: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """根据 local.yaml 的 Database 配置构建 SQLAlchemy URL 与 connect_args。

    支持新结构：
      Database:
        Type: mysql/sqlite/postgresql
        Sqlite: { Path }
        Mysql: { Host, Port, Dbname, Username, Password, Params, Driver }
        Postgresql: { Host, Port, Dbname, Username, Password, Params, Driver }

    同时兼容旧结构（MySQL 风格）：
      Database:
        Type: mysql/sqlite/postgresql
        Path/Port/Config/Dbname/Username/Password
    """
    db_type = (db_cfg.get("Type") or "sqlite").strip().lower()
    connect_args: Dict[str, Any] = {}

    if db_type == "sqlite":
        sqlite_cfg = db_cfg.get("Sqlite") or {}
        sqlite_path = sqlite_cfg.get("Path") or db_cfg.get("Path") or "word_cache.db"

        if isinstance(sqlite_path, str) and sqlite_path.startswith("sqlite:"):
            url = sqlite_path
        else:
            path_str = str(sqlite_path)
            if path_str == ":memory:":
                url = "sqlite+pysqlite:///:memory:"
            else:
                # 保持相对路径行为一致（相对当前工作目录）
                # 若给的是绝对路径则转换为绝对 file URL 形式
                p = Path(path_str)
                if p.is_absolute():
                    url = f"sqlite+pysqlite:///{p.as_posix()}"
                else:
                    url_path = path_str
                    if url_path.startswith("./"):
                        url_path = url_path[2:]
                    url = f"sqlite+pysqlite:///{url_path}"

        connect_args = {"check_same_thread": False}
        return url, connect_args

    if db_type == "mysql":
        mysql_cfg = db_cfg.get("Mysql") or {}
        host = mysql_cfg.get("Host") or db_cfg.get("Path") or "127.0.0.1"
        port = _to_int(mysql_cfg.get("Port") or db_cfg.get("Port"), 3306)
        dbname = mysql_cfg.get("Dbname") or db_cfg.get("Dbname") or "translate_transfer"
        username = mysql_cfg.get("Username") or db_cfg.get("Username") or "root"
        password = mysql_cfg.get("Password") if mysql_cfg.get("Password") is not None else db_cfg.get("Password")
        password = "" if password is None else str(password)
        params = mysql_cfg.get("Params") or db_cfg.get("Config") or ""
        driver = (mysql_cfg.get("Driver") or db_cfg.get("Driver") or "pymysql").strip()

        auth = f"{quote_plus(str(username))}:{quote_plus(password)}"
        url = f"mysql+{driver}://{auth}@{host}:{port}/{dbname}"
        if params:
            url += "?" + str(params).lstrip("?")
        return url, connect_args

    if db_type in {"postgresql", "postgres"}:
        pg_cfg = db_cfg.get("Postgresql") or {}
        host = pg_cfg.get("Host") or db_cfg.get("Path") or "127.0.0.1"
        port = _to_int(pg_cfg.get("Port") or db_cfg.get("Port"), 5432)
        dbname = pg_cfg.get("Dbname") or db_cfg.get("Dbname") or "translate_transfer"
        username = pg_cfg.get("Username") or db_cfg.get("Username") or "postgres"
        password = pg_cfg.get("Password") if pg_cfg.get("Password") is not None else db_cfg.get("Password")
        password = "" if password is None else str(password)
        params = pg_cfg.get("Params") or db_cfg.get("Config") or ""
        driver = (pg_cfg.get("Driver") or db_cfg.get("Driver") or "psycopg2").strip()

        auth = f"{quote_plus(str(username))}:{quote_plus(password)}"
        url = f"postgresql+{driver}://{auth}@{host}:{port}/{dbname}"
        if params:
            url += "?" + str(params).lstrip("?")
        return url, connect_args

    raise ValueError(f"不支持的数据库类型: {db_type!r}（支持 mysql/sqlite/postgresql）")


def _create_engine_from_local_yaml() -> "Any":
    local_cfg = _load_local_yaml()
    db_cfg = (local_cfg.get("Database") or {}) if isinstance(local_cfg, dict) else {}
    url, connect_args = _build_database_url(db_cfg)

    try:
        if connect_args:
            return create_engine(url, connect_args=connect_args)
        return create_engine(url)
    except ModuleNotFoundError as e:
        # 常见：postgresql 需要 psycopg2/psycopg，mysql 需要 pymysql
        raise ModuleNotFoundError(
            f"数据库驱动未安装：{e}. 请根据 Database.Type 安装对应驱动后重试。"
        ) from e

# 创建会话工厂
engine = _create_engine_from_local_yaml()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()

# 获取数据库会话
def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
