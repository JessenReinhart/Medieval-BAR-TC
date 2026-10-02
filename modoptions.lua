return {
  {
    key = "deathmode",
    name = "Game End Condition",
    desc = "Determines what causes game over",
    type = "list",
    def = "neverend",
    items = {
      { key = "neverend", name = "Never End", desc = "Game never ends automatically" },
    },
  },
  {
    key = "medievaltest",
    name = "Phase 1 Medieval Combat Test",
    desc = "Enable synced test forces, combat, and formation command",
    type = "bool",
    def = true,
  },
  {
    key = "medievaltestcount",
    name = "Phase 1 Total Combatants",
    desc = "Total combatants spawned across both teams (200 to 1000)",
    type = "number",
    def = 200,
    min = 200,
    max = 1000,
    step = 1,
  },
}
