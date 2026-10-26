-- WNBA & NBA fan demand: SQL used for data checks and first-look summaries
-- Database: data/attendance.db (tables wnba_games, nba_games), built by prep.py

-- 1. Games and attendance range per WNBA season
SELECT season, COUNT(*) AS games, ROUND(AVG(attendance)) AS avg_att,
       MIN(attendance) AS min_att, MAX(attendance) AS max_att
FROM wnba_games
GROUP BY season
ORDER BY season;

-- 2. No duplicate games in either table
SELECT 'wnba' AS league, COUNT(*) - COUNT(DISTINCT game_id) AS duplicates FROM wnba_games
UNION ALL
SELECT 'nba', COUNT(*) - COUNT(DISTINCT game_id) FROM nba_games;

-- 3. Every Fever game since 2024 is tagged: Clark played or did not
SELECT season, SUM(clark_played) AS clark_played, SUM(fever_no_clark) AS fever_without_clark,
       SUM(fever_game) AS fever_games
FROM wnba_games
WHERE season >= 2024
GROUP BY season;

-- 4. Average crowd per season, both leagues side by side
SELECT n.season, ROUND(AVG(n.attendance)) AS nba_avg,
       (SELECT ROUND(AVG(w.attendance)) FROM wnba_games w WHERE w.season = n.season) AS wnba_avg
FROM nba_games n
GROUP BY n.season
ORDER BY n.season;

-- 5. Fever road games vs each home team's usual (non-Fever) crowd, by season
WITH usual AS (
  SELECT season, home_display_name, AVG(attendance) AS usual_att
  FROM wnba_games
  WHERE fever_game = 0
  GROUP BY season, home_display_name
)
SELECT g.season, COUNT(*) AS fever_road_games,
       ROUND(AVG(g.attendance)) AS avg_fever_road_att,
       ROUND(AVG(u.usual_att)) AS avg_usual_att,
       ROUND(AVG(g.attendance * 1.0 / u.usual_att - 1), 3) AS mean_lift
FROM wnba_games g
JOIN usual u ON u.season = g.season AND u.home_display_name = g.home_display_name
WHERE g.fever_away = 1
GROUP BY g.season
ORDER BY g.season;

-- 6. Fever road games moved to a bigger arena since 2024
SELECT season, game_date, home_display_name, venue_full_name, attendance, clark_played
FROM wnba_games
WHERE fever_away = 1 AND relocated = 1 AND season >= 2024
ORDER BY attendance DESC;

-- 7. Weekend vs weekday crowds, WNBA 2025-2026
SELECT season, weekend, COUNT(*) AS games, ROUND(AVG(attendance)) AS avg_att
FROM wnba_games
WHERE season >= 2025
GROUP BY season, weekend;

-- 8. Expansion teams' crowds
SELECT season, home_display_name, COUNT(*) AS games, ROUND(AVG(attendance)) AS avg_att, MAX(attendance) AS max_att
FROM wnba_games
WHERE expansion_team = 1
GROUP BY season, home_display_name;
