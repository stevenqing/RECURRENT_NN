# M2.0 Operator Competence Probe

Verdict: `NEEDS_OPERATOR_FIX`

## Overall

- parse_success_rate: `0.90625`
- forced_recall: `0.1935483870967742`
- raw_precision: `0.10256410256410256`
- fixpoint_rounds: `0.5`
- fixpoint_reach_rate: `0.3125`
- status_contradiction_recall: `None`
- branch: `{"mrv": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 3.857142857142857, "n": 7, "parse_failures": 0, "solve_rate": 1.0}, "qwen_guess": {"invalid_guesses": 5, "mean_nodes_to_solve_or_cap": 4.428571428571429, "n": 7, "parse_failures": 0, "solve_rate": 1.0}, "random": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 4.142857142857143, "n": 7, "parse_failures": 0, "solve_rate": 1.0}}`

## By Task

### general_sat
- probe: `{"filter_dropped": 35, "fixpoint_reach_rate": 0.375, "forced_recall": 0.14285714285714285, "mean_fixpoint_rounds": 0.25, "n": 8, "parse_success_rate": 1.0, "raw_precision": 0.027777777777777776, "status_contradiction_recall": null}`
- branch: `{"mrv": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 5.5, "n": 2, "parse_failures": 0, "solve_rate": 1.0}, "qwen_guess": {"invalid_guesses": 4, "mean_nodes_to_solve_or_cap": 7.5, "n": 2, "parse_failures": 0, "solve_rate": 1.0}, "random": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 8, "n": 2, "parse_failures": 0, "solve_rate": 1.0}}`
### graph_coloring
- probe: `{"filter_dropped": 6, "fixpoint_reach_rate": 0.75, "forced_recall": 0.6666666666666666, "mean_fixpoint_rounds": 0.375, "n": 8, "parse_success_rate": 1.0, "raw_precision": 0.4, "status_contradiction_recall": null}`
- branch: `{"mrv": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 6, "n": 2, "parse_failures": 0, "solve_rate": 1.0}, "qwen_guess": {"invalid_guesses": 1, "mean_nodes_to_solve_or_cap": 6, "n": 2, "parse_failures": 0, "solve_rate": 1.0}, "random": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 4.5, "n": 2, "parse_failures": 0, "solve_rate": 1.0}}`
### horn_sat
- probe: `{"filter_dropped": 33, "fixpoint_reach_rate": 0.0, "forced_recall": 0.4, "mean_fixpoint_rounds": 1.25, "n": 8, "parse_success_rate": 1.0, "raw_precision": 0.15384615384615385, "status_contradiction_recall": null}`
- branch: `{"mrv": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 1, "n": 1, "parse_failures": 0, "solve_rate": 1.0}, "qwen_guess": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 1, "n": 1, "parse_failures": 0, "solve_rate": 1.0}, "random": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 1, "n": 1, "parse_failures": 0, "solve_rate": 1.0}}`
### sudoku_4x4
- probe: `{"filter_dropped": 31, "fixpoint_reach_rate": 0.125, "forced_recall": 0.029411764705882353, "mean_fixpoint_rounds": 0.125, "n": 8, "parse_success_rate": 0.625, "raw_precision": 0.03125, "status_contradiction_recall": null}`
- branch: `{"mrv": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 1.5, "n": 2, "parse_failures": 0, "solve_rate": 1.0}, "qwen_guess": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 1.5, "n": 2, "parse_failures": 0, "solve_rate": 1.0}, "random": {"invalid_guesses": 0, "mean_nodes_to_solve_or_cap": 1.5, "n": 2, "parse_failures": 0, "solve_rate": 1.0}}`
