GOALS = []


def add_goal(goal):
    if goal not in GOALS:
        GOALS.append(goal)


def get_goals():
    return GOALS