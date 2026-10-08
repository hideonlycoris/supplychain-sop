"""user_store 的单元测试（用内存假客户端，不碰真库）

覆盖：建号 / 改权限 / 改密码 / 删号 / 登录校验 / 表不存在时的降级。

运行: python -X utf8 test_user_store.py
"""
import copy

import user_store


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """只模拟 user_store 用到的那几个链式调用"""

    def __init__(self, rows, op, payload=None, filters=None):
        self._rows, self._op = rows, op
        self._payload = payload or {}
        self._filters = filters or []

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def execute(self):
        if self._op == "select":
            out = [copy.deepcopy(r) for r in self._rows]
            for col, val in self._filters:
                out = [r for r in out if r.get(col) == val]
            return _Result(out)
        if self._op == "upsert":
            key = self._payload["username"]
            for i, r in enumerate(self._rows):
                if r.get("username") == key:
                    merged = dict(r)
                    merged.update(self._payload)
                    self._rows[i] = merged
                    return _Result([copy.deepcopy(merged)])
            self._rows.append(dict(self._payload))
            return _Result([copy.deepcopy(self._payload)])
        if self._op == "delete":
            before = len(self._rows)
            for col, val in self._filters:
                self._rows[:] = [r for r in self._rows if r.get(col) != val]
            return _Result([{"deleted": before - len(self._rows)}])
        raise AssertionError(f"unsupported op {self._op}")


class FakeClient:
    def __init__(self, rows=None, missing_table=False):
        self.rows = rows if rows is not None else []
        self.missing_table = missing_table

    def table(self, name):
        assert name == user_store.TABLE
        if self.missing_table:
            raise Exception(
                "{'message': \"Could not find the table 'public.app_users' in "
                "the schema cache\", 'code': 'PGRST205'}"
            )
        return self

    def select(self, *_a, **_k):
        return _Query(self.rows, "select")

    def upsert(self, payload, on_conflict=""):
        assert on_conflict == "username", on_conflict
        return _Query(self.rows, "upsert", payload)

    def delete(self):
        return _Query(self.rows, "delete")


def test_create_then_login():
    c = FakeClient()
    acc = user_store.upsert_user(c, username="张三", password="mima1234",
                                 department=None, owned_skus=["USWBLM0100260-割草机"])
    assert acc["kind"] == "personal"
    assert acc["department"] is None
    assert acc["owned_skus"] == ["USWBLM0100260-割草机"]
    # 密码绝不能明文落库
    assert "mima1234" not in str(c.rows)
    assert user_store.authenticate(c, "张三", "mima1234") is not None
    assert user_store.authenticate(c, "张三", "mima1235") is None
    assert user_store.authenticate(c, "李四", "mima1234") is None
    print("OK  建号 + 登录校验（正确密码通过、错密码/不存在的账号拒绝、库内无明文）")


def test_update_ownership_and_department():
    c = FakeClient()
    user_store.upsert_user(c, username="李四", password="abcd1234", department="五部",
                           owned_skus=["A-割草机"])
    user_store.upsert_user(c, username="李四", password="", department=None,
                           owned_skus=["A-割草机", "B-发电机"])
    acc = user_store.find_user(c, "李四")
    assert acc["department"] is None, acc
    assert acc["owned_skus"] == ["A-割草机", "B-发电机"], acc
    # 密码留空 = 不改
    assert user_store.authenticate(c, "李四", "abcd1234") is not None
    print("OK  改负责项目/取消部门；密码留空不被清掉")


def test_reset_password():
    c = FakeClient()
    user_store.upsert_user(c, username="王五", password="old12345")
    user_store.upsert_user(c, username="王五", password="new12345")
    assert user_store.authenticate(c, "王五", "old12345") is None
    assert user_store.authenticate(c, "王五", "new12345") is not None
    print("OK  重置密码后旧密码立即失效")


def test_delete_user():
    c = FakeClient()
    user_store.upsert_user(c, username="赵六", password="pass1234")
    assert user_store.delete_user(c, "赵六") is True
    assert user_store.find_user(c, "赵六") is None
    print("OK  删除账号后登录即失效")


def test_validation():
    c = FakeClient()
    try:
        user_store.upsert_user(c, username="", password="pass1234")
        raise AssertionError("空用户名应报错")
    except ValueError:
        pass
    try:
        user_store.upsert_user(c, username="短", password="123")
        raise AssertionError("过短密码应报错")
    except ValueError:
        pass
    try:
        user_store.upsert_user(c, username="新号", password="")
        raise AssertionError("新账号没密码应报错")
    except ValueError:
        pass
    print("OK  空用户名 / 少于 6 位密码 / 新账号无密码 全部拦下")


def test_missing_table_degrades():
    user_store.reset_state()
    c = FakeClient(missing_table=True)
    assert user_store.list_personal_users(c) == []
    assert "setup_app_users.sql" in user_store.table_issue()
    # 老账号登录路径不依赖这张表，所以这里返回 [] 就是正确行为
    assert user_store.authenticate(c, "张三", "x") is None
    user_store.reset_state()
    print("OK  表还没建时降级成「没有个人账号」，并给出建表提示")


def test_disabled_accounts_are_hidden():
    c = FakeClient(rows=[{
        "username": "停用", "salt": "s", "password_hash": "h",
        "department": None, "owned_skus": "[]", "is_active": False,
    }])
    assert user_store.list_personal_users(c) == []
    print("OK  停用的账号不出现在登录列表")


if __name__ == "__main__":
    test_create_then_login()
    test_update_ownership_and_department()
    test_reset_password()
    test_delete_user()
    test_validation()
    test_missing_table_degrades()
    test_disabled_accounts_are_hidden()
    print("\n全部通过 ✅")
