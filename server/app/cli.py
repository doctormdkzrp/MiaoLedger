"""命令行小工具：看谁在用、建账号、重置密码、提管理员。

用法（在 server/ 目录下）：
  python -m app.cli users
  python -m app.cli add-user demo 123456 演示账号
  python -m app.cli reset-pin demo 654321
  python -m app.cli promote demo

promote 用于把已注册的账号提为管理员（等价于启动时配置 ADMIN_USERNAME）。
"""
import sys

from sqlalchemy import select

from .auth import ROLE_ADMIN, ROLE_USER, hash_pin, promote_admin
from .common import seed_user
from .db import SessionLocal, init_db
from .models import Device, Txn, User


def main(argv: list[str]) -> int:
    init_db()
    db = SessionLocal()
    cmd = argv[0] if argv else "users"

    if cmd == "users":
        rows = db.scalars(select(User)).all()
        if not rows:
            print("还没有账号")
        for u in rows:
            n_txn = len(db.scalars(select(Txn).where(Txn.user_id == u.id)).all())
            n_dev = len(db.scalars(select(Device).where(Device.user_id == u.id)).all())
            role = u.role or ROLE_USER
            print(
                f"{u.username:12s} {u.display_name:8s} {role:5s} 账 {n_txn:5d} 笔  设备 {n_dev} 台"
            )
        return 0

    if cmd == "add-user":
        if len(argv) < 3:
            print("用法: add-user <账号> <密码> [显示名]")
            return 2
        username, pin = argv[1], argv[2]
        if db.scalar(select(User).where(User.username == username)):
            print("这个账号已存在")
            return 1
        u = User(
            username=username,
            pin_hash=hash_pin(pin),
            display_name=argv[3] if len(argv) > 3 else username,
            role=ROLE_USER,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        seed_user(db, u)
        print(f"建好了：{username}（默认一个账本、4 个账户、15 个分类）")
        return 0

    if cmd == "reset-pin":
        if len(argv) < 3:
            print("用法: reset-pin <账号> <新密码>")
            return 2
        u = db.scalar(select(User).where(User.username == argv[1]))
        if u is None:
            print("没这个账号")
            return 1
        u.pin_hash = hash_pin(argv[2])
        for d in db.scalars(select(Device).where(Device.user_id == u.id)).all():
            db.delete(d)  # 旧 token 全部作废，强制重新登录
        db.commit()
        print("密码已重置，旧设备的登录已失效")
        return 0

    if cmd == "promote":
        if len(argv) < 2:
            print("用法: promote <账号>")
            return 2
        if not promote_admin(db, argv[1]):
            print("没这个账号")
            return 1
        print(f"{argv[1]} 现在是管理员（{ROLE_ADMIN}）")
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
