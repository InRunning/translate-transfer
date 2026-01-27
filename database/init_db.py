from models.base import Base, engine, SessionLocal
from models.word_cache import WordCache


def init_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)
    print("数据库初始化完成")


def get_db_session():
    """获取数据库会话"""
    return SessionLocal()


def get_cached_word(word: str):
    """从缓存中获取单词翻译结果

    Args:
        word: 要查询的单词

    Returns:
        如果找到缓存则返回字典，否则返回None
    """
    session = get_db_session()
    try:
        result = session.query(WordCache).filter(
            WordCache.word == word.lower()
        ).first()

        if result:
            return {
                'word': result.word,
                'translation_result': result.translation_result
            }
        return None
    finally:
        session.close()


def cache_word_translation(word: str, translation_result: str):
    """缓存单词翻译结果

    Args:
        word: 要缓存的单词
        translation_result: 翻译结果

    Returns:
        成功返回True，失败返回False
    """
    session = get_db_session()
    try:
        # 查找是否已存在
        existing = session.query(WordCache).filter(
            WordCache.word == word.lower()
        ).first()

        if existing:
            # 更新现有记录
            existing.translation_result = translation_result
        else:
            # 创建新记录
            new_cache = WordCache(
                word=word.lower(),
                translation_result=translation_result
            )
            session.add(new_cache)

        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"数据库错误: {e}")
        return False
    finally:
        session.close()