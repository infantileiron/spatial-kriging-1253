import os,sys,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 本地测试使用临时文件SQLite；模型里的MySQL二进制排序规则在每个SQLite连接上注册为同名no-op。
_db_path=os.path.join(tempfile.mkdtemp(prefix="spatial-test-"),"test.sqlite")
os.environ.setdefault("DATABASE_URL",f"sqlite:///{_db_path}")
from sqlalchemy.event import listens_for
from src.config.database import engine
@listens_for(engine,"connect")
def _sqlite_collation(dbapi_conn,_):
 dbapi_conn.create_collation("utf8mb4_bin",lambda a,b:(a>b)-(a<b))
