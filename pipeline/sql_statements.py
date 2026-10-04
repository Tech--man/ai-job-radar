"""SQL 语句常量与字段清单（全部为字面量，配合命名占位符参数绑定使用）。

分离成独立模块便于审计：本文件中没有任何外部输入参与构造，运行时零拼接。
lang 字段仅存 processed JSON，不进 SQLite（SQLite 保持原始 schema 作为存档）。
"""

INSERT_SQL = (
    "INSERT INTO jobs (source, source_id, posted_date, month, company, company_norm, title,"
    " is_ai, role, roles_all, skills, is_remote, remote_kind, city, country,"
    " salary_min_usd, salary_max_usd, salary_currency, salary_period, salary_raw, salary_conf,"
    " text_clean, url, dedup_key)"
    " VALUES (:source, :source_id, :posted_date, :month, :company, :company_norm, :title,"
    " :is_ai, :role, :roles_all, :skills, :is_remote, :remote_kind, :city, :country,"
    " :salary_min_usd, :salary_max_usd, :salary_currency, :salary_period, :salary_raw,"
    " :salary_conf, :text_clean, :url, :dedup_key)"
)

DDL_JOBS = (
    "CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, source TEXT NOT NULL,"
    " source_id TEXT, posted_date TEXT, month TEXT, company TEXT, company_norm TEXT,"
    " title TEXT, is_ai INTEGER, role TEXT, roles_all TEXT, skills TEXT, is_remote INTEGER,"
    " remote_kind TEXT, city TEXT, country TEXT, salary_min_usd REAL, salary_max_usd REAL,"
    " salary_currency TEXT, salary_period TEXT, salary_raw TEXT, salary_conf TEXT,"
    " text_clean TEXT, url TEXT, dedup_key TEXT)"
)
DDL_IDX_ROLE = "CREATE INDEX IF NOT EXISTS idx_jobs_role ON jobs(role)"
DDL_IDX_AI = "CREATE INDEX IF NOT EXISTS idx_jobs_ai ON jobs(is_ai)"
DDL_IDX_MONTH = "CREATE INDEX IF NOT EXISTS idx_jobs_month ON jobs(month)"
DDL_META = "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
DELETE_JOBS = "DELETE FROM jobs"
DELETE_META = "DELETE FROM meta"
META_INSERT = "INSERT INTO meta (key, value) VALUES (:key, :value)"

FIELDS = ["source", "source_id", "posted_date", "month", "company", "company_norm", "title",
          "is_ai", "role", "roles_all", "skills", "is_remote", "remote_kind", "city", "country",
          "salary_min_usd", "salary_max_usd", "salary_currency", "salary_period", "salary_raw",
          "salary_conf", "text_clean", "url", "dedup_key"]
