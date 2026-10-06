--------------------------------------------------------------------------------
--  file:    draw.lua
--  brief:   the UNSYNCED half of the LuaRules split handle (Phase 1)
--
--  Why this file must exist:
--  Recoil's LuaRules is a CSplitLuaHandle. InitSynced() loads
--  LuaRules/main.lua (the synced half, our gadget manager). InitUnsynced()
--  then loads LuaRules/draw.lua; if that file is missing or empty,
--  CSplitLuaHandle::InitUnsynced() calls KillLua() and destroys BOTH halves
--  (rts/Lua/LuaHandleSynced.cpp:2435). That left luaRules == nullptr in
--  CGame (infolog: "[Game::Load][lua{Rules,Gaia}={0000000000000000,...}]"),
--  so no synced callin (GameFrame, GameStart, ...) ever dispatched and the
--  frame-30 test spawn never ran. Shipping this file keeps the handle alive.
--
--  In the unsynced half, Script.GetName() returns "LuaRulesUS"; gadgets.lua
--  strips the trailing "US" so the same manager loads unsynced gadgets.
--  Our synced-only gadgets early-return here via IsSyncedCode().
--------------------------------------------------------------------------------

VFS.Include(Script.GetName() .. "/gadgets.lua", nil, VFS.ZIP_ONLY)
