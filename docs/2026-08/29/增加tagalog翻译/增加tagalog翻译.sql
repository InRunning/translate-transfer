-- Tagalog 翻译端口：单词缓存按目标语言隔离
-- 适用：MySQL 5.7+ / 8.0+
-- 执行前：请先连接到 translate-transfer 实际使用的数据库，并备份 word_cache 表。
-- 本脚本不会删除缓存数据；已有记录将标记为 zh-CN。

-- 1. 仅在字段尚不存在时新增 target_language。
SET @schema_name := DATABASE();
SET @has_target_language := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'word_cache'
    AND COLUMN_NAME = 'target_language'
);
SET @sql := IF(
  @has_target_language = 0,
  'ALTER TABLE `word_cache` ADD COLUMN `target_language` VARCHAR(16) NOT NULL DEFAULT ''zh-CN'' AFTER `word`',
  'SELECT ''target_language column already exists'' AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 2. 兼容早期人工迁移：将 NULL 或空值统一修正为中文语言标识。
UPDATE `word_cache`
SET `target_language` = 'zh-CN'
WHERE `target_language` IS NULL OR `target_language` = '';

-- 3. 删除「仅 word 一列」的非主键唯一索引。
--    GORM 生成的索引名会因版本和历史 DDL 不同而变化，因此按索引定义识别，而非写死索引名。
SET @drop_unique_word_indexes := (
  SELECT GROUP_CONCAT(
    CONCAT('DROP INDEX `', REPLACE(index_name, '`', '``'), '`')
    ORDER BY index_name
    SEPARATOR ', '
  )
  FROM (
    SELECT INDEX_NAME AS index_name
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = @schema_name
      AND TABLE_NAME = 'word_cache'
      AND NON_UNIQUE = 0
      AND INDEX_NAME <> 'PRIMARY'
    GROUP BY INDEX_NAME
    HAVING COUNT(*) = 1
       AND MIN(COLUMN_NAME) = 'word'
  ) AS unique_word_indexes
);
SET @sql := IF(
  @drop_unique_word_indexes IS NULL OR @drop_unique_word_indexes = '',
  'SELECT ''single-column unique index on word does not exist'' AS message',
  CONCAT('ALTER TABLE `word_cache` ', @drop_unique_word_indexes)
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 4. 仅在组合唯一索引不存在时创建它。
SET @has_language_word_unique_index := (
  SELECT COUNT(*)
  FROM (
    SELECT INDEX_NAME
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = @schema_name
      AND TABLE_NAME = 'word_cache'
      AND NON_UNIQUE = 0
      AND INDEX_NAME <> 'PRIMARY'
    GROUP BY INDEX_NAME
    HAVING GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') = 'target_language,word'
  ) AS language_word_unique_indexes
);
SET @sql := IF(
  @has_language_word_unique_index = 0,
  'ALTER TABLE `word_cache` ADD UNIQUE INDEX `uniq_target_language_word` (`target_language`, `word`)',
  'SELECT ''unique index on (target_language, word) already exists'' AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 5. 验证：应看到 target_language 字段和 (target_language, word) 的唯一索引。
SHOW COLUMNS FROM `word_cache` LIKE 'target_language';
SHOW INDEX FROM `word_cache`;

-- 应用代码配套要求：
-- 1) 中文端口读取/写入 target_language = 'zh-CN'；Tagalog 端口使用 target_language = 'tl'。
-- 2) 内存缓存键也必须包含 target_language，例如 "tl:example"。
