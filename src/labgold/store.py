"""Penyimpanan: MongoDB Atlas (produksi) atau memori (uji coba)."""
import datetime as dt
import json


def _default(o):
    if hasattr(o, "item"):          # tipe numpy -> tipe Python
        return o.item()
    raise TypeError(f"tidak bisa menyimpan {type(o)}")


def clean(obj):
    return json.loads(json.dumps(obj, default=_default))


class MemoryStore:
    def __init__(self):
        self.kv, self._signals, self._decisions, self._lock = {}, {}, [], 0

    def get(self, key):
        v = self.kv.get(key)
        return None if v is None else clean(v)

    def set(self, key, value):
        self.kv[key] = clean(value)

    def add_signal(self, s):
        self._signals[s["id"]] = clean(s)

    def update_signal(self, s):
        self._signals[s["id"]] = clean(s)

    def signals(self, statuses=None, kinds=None):
        out = [clean(s) for s in self._signals.values()]
        return [s for s in out if (statuses is None or s["status"] in statuses) and (kinds is None or s["kind"] in kinds)]

    def add_decision(self, doc):
        self._decisions.append(clean(doc))

    def decisions_since(self, ts):
        return [d for d in self._decisions if d["ts"] >= ts]

    def acquire_lock(self, now_ts, ttl=480):
        if self._lock > now_ts:
            return False
        self._lock = now_ts + ttl
        return True

    def release_lock(self):
        self._lock = 0

    def storage_ratio(self):
        return None


class MongoStore:
    def __init__(self, url, dbname):
        from pymongo import MongoClient          # diimpor di sini agar uji tanpa pymongo tetap jalan
        self.client = MongoClient(url, serverSelectionTimeoutMS=20000)
        self.db = self.client[dbname]
        self.db.command("ping")
        self.db.decisions.create_index("created_at", expireAfterSeconds=180 * 86400)   # keputusan disimpan 180 hari
        self.db.signals.create_index("id", unique=True)

    def get(self, key):
        d = self.db.state.find_one({"_id": key})
        return d["v"] if d else None

    def set(self, key, value):
        self.db.state.replace_one({"_id": key}, {"_id": key, "v": clean(value)}, upsert=True)

    def add_signal(self, s):
        self.db.signals.insert_one(clean(s))

    def update_signal(self, s):
        d = clean(s)
        d.pop("_id", None)
        self.db.signals.replace_one({"id": s["id"]}, d)

    def signals(self, statuses=None, kinds=None):
        q = {}
        if statuses is not None:
            q["status"] = {"$in": list(statuses)}
        if kinds is not None:
            q["kind"] = {"$in": list(kinds)}
        out = []
        for d in self.db.signals.find(q):
            d.pop("_id", None)
            out.append(d)
        return out

    def add_decision(self, doc):
        d = clean(doc)
        d["created_at"] = dt.datetime.now(dt.timezone.utc)
        self.db.decisions.insert_one(d)

    def decisions_since(self, ts):
        out = []
        for d in self.db.decisions.find({"ts": {"$gte": ts}}):
            d.pop("_id", None)
            d.pop("created_at", None)
            out.append(d)
        return out

    def acquire_lock(self, now_ts, ttl=480):
        from pymongo.errors import DuplicateKeyError
        try:
            if self.db.state.find_one_and_update({"_id": "lock", "until": {"$lt": now_ts}}, {"$set": {"until": now_ts + ttl}}):
                return True
            self.db.state.insert_one({"_id": "lock", "until": now_ts + ttl})
            return True
        except DuplicateKeyError:
            return False

    def release_lock(self):
        self.db.state.update_one({"_id": "lock"}, {"$set": {"until": 0}})

    def storage_ratio(self):
        """Perkiraan pemakaian ruang cluster gratis (M0 = 512 MB); None bila tidak bisa dibaca."""
        try:
            return sum(d.get("sizeOnDisk", 0) for d in self.client.list_databases()) / (512 * 1024 * 1024)
        except Exception:  # noqa: BLE001
            return None
