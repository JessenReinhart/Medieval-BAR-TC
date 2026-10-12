-- Sound definitions for Medieval-BAR-TC
-- Maps sound aliases and configurations to extracted 0 A.D. audio assets.

local Sounds = {
	SoundItems = {
		-- Combat / Weapons
		sword_swing = {
			file = "sounds/weapons/sword_swing.ogg",
			gain = 1.0,
			pitch = 1.0,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 12000,
		},
		sword_hit = {
			file = "sounds/weapons/sword_hit.ogg",
			gain = 1.0,
			pitch = 1.0,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 12000,
		},
		spear_thrust = {
			file = "sounds/weapons/spear_thrust.ogg",
			gain = 0.9,
			pitch = 1.0,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 12000,
		},
		spear_hit = {
			file = "sounds/weapons/spear_hit.ogg",
			gain = 1.0,
			pitch = 1.0,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 12000,
		},
		bow_shoot = {
			file = "sounds/weapons/bow_shoot.ogg",
			gain = 1.0,
			pitch = 1.0,
			pitchmod = 0.15,
			in3d = true,
			maxdist = 15000,
		},
		arrow_hit = {
			file = "sounds/weapons/arrow_hit.ogg",
			gain = 0.9,
			pitch = 1.0,
			pitchmod = 0.15,
			in3d = true,
			maxdist = 15000,
		},
		crossbow_shoot = {
			file = "sounds/weapons/crossbow_shoot.ogg",
			gain = 1.1,
			pitch = 0.95,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 16000,
		},
		bolt_hit = {
			file = "sounds/weapons/bolt_hit.ogg",
			gain = 1.0,
			pitch = 1.0,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 16000,
		},
		lance_charge = {
			file = "sounds/weapons/lance_charge.ogg",
			gain = 1.2,
			pitch = 0.9,
			pitchmod = 0.05,
			in3d = true,
			maxdist = 15000,
		},
		lance_hit = {
			file = "sounds/weapons/lance_hit.ogg",
			gain = 1.2,
			pitch = 1.0,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 15000,
		},
		catapult_shoot = {
			file = "sounds/weapons/catapult_shoot.ogg",
			gain = 1.3,
			pitch = 0.9,
			pitchmod = 0.05,
			in3d = true,
			maxdist = 25000,
		},
		catapult_hit = {
			file = "sounds/weapons/catapult_hit.ogg",
			gain = 1.4,
			pitch = 1.0,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 25000,
		},
		dagger_hit = {
			file = "sounds/weapons/dagger_hit.ogg",
			gain = 0.8,
			pitch = 1.1,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 10000,
		},

		-- Economy & Gathering
		wood_chop = {
			file = "sounds/economy/wood_chop.ogg",
			gain = 0.9,
			pitch = 1.0,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 10000,
		},
		stone_mine = {
			file = "sounds/economy/stone_mine.ogg",
			gain = 0.9,
			pitch = 1.0,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 10000,
		},
		construction = {
			file = "sounds/economy/construction.ogg",
			gain = 0.85,
			pitch = 1.0,
			pitchmod = 0.1,
			in3d = true,
			maxdist = 10000,
		},
		haul_cart = {
			file = "sounds/economy/haul_cart.ogg",
			gain = 0.7,
			pitch = 1.0,
			pitchmod = 0.05,
			in3d = true,
			maxdist = 8000,
		},

		-- UI & Alerts
		alarm_under_attack = {
			file = "sounds/ui/alarm_under_attack.ogg",
			gain = 1.2,
			in3d = false,
		},
		building_complete = {
			file = "sounds/ui/building_complete.ogg",
			gain = 1.0,
			in3d = false,
		},
		unit_select = {
			file = "sounds/ui/unit_select.ogg",
			gain = 0.9,
			in3d = false,
		},
	},
}

return Sounds
