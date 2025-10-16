# 调用流程：zotero_proxy

1. 在 [../../app.py#L66](../../app.py#L66) 调用 `request.get_json()` Flask内置方法
2. 在 [../../app.py#L74](../../app.py#L74) 调用 `is_word` [../../app.py#L29](../../app.py#L29)
3. 在 [../../app.py#L75](../../app.py#L75) 调用 `call_deepseek_api` [../../app.py#L33](../../app.py#L33)
   3.1 在 [../../app.py#L58](../../app.py#L58) 调用 `requests.post` 外部库方法
4. 在 [../../app.py#L80](../../app.py#L80) 调用 `jsonify` Flask内置方法