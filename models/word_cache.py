from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from sqlalchemy.sql import func
from .base import Base


class WordCache(Base):
    """单词翻译缓存表"""
    __tablename__ = 'word_cache'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    word = Column(String(100), unique=True, nullable=False, index=True, comment='单词')
    translation_result = Column(Text, nullable=False, comment='翻译结果')
    created_at = Column(DateTime, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False, comment='更新时间')

    # 创建索引
    __table_args__ = (
        Index('idx_word', 'word'),
        {'comment': '单词翻译缓存表'}
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'word': self.word,
            'translation_result': self.translation_result,
            'created_at': self.created_at.isoformat() if self.created_at else None, # type: ignore
            'updated_at': self.updated_at.isoformat() if self.updated_at else None # type: ignore
        }

    def __repr__(self):
        return f"<WordCache(word='{self.word}', id={self.id})>"