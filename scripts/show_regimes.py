"""Print the historical regime table (legal eras + statistical pool groups)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from fortuna.rules import load_regimes  # noqa: E402


def matrix(r) -> str:
    base = f"{r.main_ball_count}/{r.main_ball_max}"
    if r.special_ball_count:
        base += f" + {r.special_ball_count}/{r.special_ball_max}"
    return base


def main() -> int:
    game_filter = sys.argv[1] if len(sys.argv) > 1 else None
    regimes = load_regimes(REPO_ROOT / "metadata" / "game_regimes.csv")
    if game_filter:
        regimes = [r for r in regimes if r.game_id == game_filter]
    current_game = None
    for r in sorted(regimes, key=lambda x: (x.game_id, x.span_start)):
        if r.game_id != current_game:
            current_game = r.game_id
            print(f"\n=== {current_game} ===")
            print(f"{'regime':10} {'pool':7} {'class':15} {'first draw':12} {'last draw':12} "
                  f"{'matrix':12} {'days':12} {'price':6} {'verified':20}")
        print(f"{r.regime_id:10} {r.statistical_regime_id:7} "
              f"{r.change_classification.value:15} "
              f"{str(r.span_start):12} {str(r.span_end or 'present'):12} "
              f"{matrix(r):12} {';'.join(r.drawing_days):12} "
              f"{str(r.ticket_price or ''):6} {r.verification_status.value:20}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
