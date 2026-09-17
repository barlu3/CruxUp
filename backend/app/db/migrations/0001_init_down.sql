-- [W0-1a] Reversal of 0001_init.sql.
--
-- Dropped in reverse dependency order. Indexes and constraints go with their
-- tables; pgcrypto is left installed because other migrations may rely on it
-- and dropping a shared extension is not this migration's business.

BEGIN;

DROP TABLE IF EXISTS recommendation;
DROP TABLE IF EXISTS user_survey;
DROP TABLE IF EXISTS shoe_size_map;
DROP TABLE IF EXISTS shoe_alias;
DROP TABLE IF EXISTS shoe;

COMMIT;
