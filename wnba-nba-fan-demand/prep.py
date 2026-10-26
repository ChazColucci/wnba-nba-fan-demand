"""Build clean game-level attendance tables for WNBA (2019, 2022-2026) and NBA (2015-2026).
Outputs: data/wnba_games.csv, data/nba_games.csv, data/attendance.db, data/checks.json
"""
import json, sqlite3, os
import pandas as pd, numpy as np

W = 'raw/wehoop-wnba-data/wnba'  # clone github.com/sportsdataverse/wehoop-wnba-data into raw/
N = 'raw/hoopR-nba-data/nba'  # clone github.com/sportsdataverse/hoopR-nba-data into raw/
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(OUT, exist_ok=True)
checks = {}

MAJOR_TV = {'ABC', 'CBS', 'ESPN', 'ESPN2', 'ION', 'Prime Video', 'CBSSN', 'NBC', 'Peacock', 'USA Network', 'NBCSN', 'TNT', 'truTV'}
KEEP = ['game_id', 'season', 'game_date', 'game_date_time', 'home_display_name', 'away_display_name',
        'venue_full_name', 'venue_address_city', 'attendance', 'neutral_site', 'broadcast_market',
        'broadcast_name', 'home_score', 'away_score']


def load_sched(path, seasons, fmt):
    frames = []
    for y in seasons:
        s = pd.read_parquet(f'{path}/schedules/parquet/{fmt.format(y)}.parquet')
        s = s[s.season_type == 2]  # regular season only
        frames.append(s[[c for c in KEEP if c in s.columns]])
    return pd.concat(frames, ignore_index=True)


# ---------------- WNBA ----------------
WSEAS = [2019, 2022, 2023, 2024, 2025, 2026]  # 2020 bubble (no fans) and 2021 (COVID capacity limits) excluded
w = load_sched(W, WSEAS, 'wnba_schedule_{}')
checks['wnba_raw_rows'] = len(w)
w['game_id'] = w.game_id.astype('int64')
w = w.drop_duplicates('game_id')
checks['wnba_after_dedupe'] = len(w)
# Drop All-Star games (e.g. "Team WNBA" vs "Team USA"): keep only real franchises (10+ home games in a season)
franchises = w.groupby(['season', 'home_display_name']).size()
franchises = set(franchises[franchises >= 10].index.get_level_values(1))
allstar = ~(w.home_display_name.isin(franchises) & w.away_display_name.isin(franchises))
checks['wnba_allstar_dropped'] = int(allstar.sum())
w = w[~allstar].copy()

# Caitlin Clark game status from player box scores (2024-2026)
clark = []
for y in [2024, 2025, 2026]:
    b = pd.read_parquet(f'{W}/player_box/parquet/player_box_{y}.parquet')
    c = b[(b.athlete_display_name == 'Caitlin Clark') & (b.season_type == 2)]
    clark.append(c[['game_id', 'did_not_play']])
clark = pd.concat(clark)
clark['game_id'] = clark.game_id.astype('int64')
clark['clark_played'] = (~clark.did_not_play.astype(bool)).astype(int)
w = w.merge(clark[['game_id', 'clark_played']], on='game_id', how='left')

fever = (w.home_display_name == 'Indiana Fever') | (w.away_display_name == 'Indiana Fever')
w['fever_game'] = fever.astype(int)
w['fever_home'] = (w.home_display_name == 'Indiana Fever').astype(int)
w['fever_away'] = (w.away_display_name == 'Indiana Fever').astype(int)
w['clark_played'] = w.clark_played.fillna(0).astype(int)
# Fever games from 2024 on with no Clark box-score row would be a data gap: check
gap = w[(w.season >= 2024) & fever & w.game_id.isin(clark.game_id).eq(False)]
checks['fever_games_missing_clark_row'] = int(len(gap))
w['clark_era'] = (w.season >= 2024).astype(int)
w['fever_no_clark'] = ((w.fever_game == 1) & (w.clark_era == 1) & (w.clark_played == 0)).astype(int)

# ---------------- shared features ----------------

def features(df):
    dt = pd.to_datetime(df.game_date_time, utc=True, errors='coerce')
    gd = pd.to_datetime(df.game_date)
    df['game_date'] = gd.dt.strftime('%Y-%m-%d')
    df['dow'] = gd.dt.day_name()
    df['weekend'] = gd.dt.dayofweek.isin([4, 5, 6]).astype(int)  # Fri-Sun
    df['month'] = gd.dt.month
    df['major_tv'] = df.broadcast_name.isin(MAJOR_TV).astype(int)
    df['national_tv'] = (df.broadcast_market == 'national').astype(int)
    df['neutral_site'] = df.neutral_site.fillna(False).astype(int)
    return df


w = features(w)
# Home "usual" venue = the arena a team used most that season; anything else is a relocated game
usual = (w.groupby(['season', 'home_display_name']).venue_full_name
         .agg(lambda s: s.value_counts().idxmax()).rename('usual_venue'))
w = w.join(usual, on=['season', 'home_display_name'])
w['relocated'] = ((w.venue_full_name != w.usual_venue) & (w.neutral_site == 0)).astype(int)
w['expansion_team'] = w.home_display_name.isin(['Golden State Valkyries', 'Portland Fire', 'Toronto Tempo']).astype(int)

checks['wnba_missing_or_zero_att'] = int((w.attendance.isna() | (w.attendance <= 0)).sum())
w = w[w.attendance > 0].copy()
checks['wnba_rows_final'] = len(w)
checks['wnba_att_min_max'] = [int(w.attendance.min()), int(w.attendance.max())]
checks['wnba_games_by_season'] = w.season.value_counts().sort_index().to_dict()
checks['clark_games_by_season'] = w[w.clark_played == 1].season.value_counts().sort_index().to_dict()
checks['fever_no_clark_by_season'] = w[w.fever_no_clark == 1].season.value_counts().sort_index().to_dict()

# ---------------- NBA ----------------
NSEAS = [2015, 2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025, 2026]  # 2020 bubble & 2021 limited crowds excluded
n = load_sched(N, NSEAS, 'nba_schedule_{}')
n['game_id'] = n.game_id.astype('int64')
n = n.drop_duplicates('game_id')
n = features(n)
checks['nba_missing_or_zero_att'] = int((n.attendance.isna() | (n.attendance <= 0)).sum())
n = n[(n.attendance > 0) & (n.neutral_site == 0)].copy()
# Capacity proxy: the 99th-percentile crowd each home team drew in its main arena that season
n_usual = (n.groupby(['season', 'home_display_name']).venue_full_name
           .agg(lambda s: s.value_counts().idxmax()).rename('usual_venue'))
n = n.join(n_usual, on=['season', 'home_display_name'])
n = n[n.venue_full_name == n.usual_venue].copy()  # drop international / relocated games
cap = n.groupby(['season', 'home_display_name']).attendance.quantile(0.99).rename('cap_proxy')
n = n.join(cap, on=['season', 'home_display_name'])
n['fill_rate'] = (n.attendance / n.cap_proxy).clip(upper=1.0)
checks['nba_rows_final'] = len(n)
checks['nba_games_by_season'] = n.season.value_counts().sort_index().to_dict()

# WNBA capacity proxy (same method) for comparison - main arena only
wm = w[(w.relocated == 0) & (w.neutral_site == 0)]
wcap = wm.groupby(['season', 'home_display_name']).attendance.quantile(0.99).rename('cap_proxy')
w = w.join(wcap, on=['season', 'home_display_name'])
w['fill_rate'] = np.where(w.relocated == 0, (w.attendance / w.cap_proxy).clip(upper=1.0), np.nan)

w.to_csv(f'{OUT}/wnba_games.csv', index=False)
n.to_csv(f'{OUT}/nba_games.csv', index=False)
con = sqlite3.connect(f'{OUT}/attendance.db')
w.to_sql('wnba_games', con, if_exists='replace', index=False)
n.to_sql('nba_games', con, if_exists='replace', index=False)
con.close()
json.dump(checks, open(f'{OUT}/checks.json', 'w'), indent=1, default=str)
print(json.dumps(checks, indent=1, default=str))
