# Future City-Building Architecture Integration Note

## Overview
This document records integration points for medieval settlement and economy features to follow Phase 1. BAR's energy and metal economy remains active during Phase 1 testing and will be phased out or layered in subsequent milestones.

## 1. Resources: Food, Wood, Stone, Iron
- **Storage and Flow:** Introduce discrete stockpiles managed via custom synced gadget state rather than relying exclusively on Spring's dual resource pool (energy/metal).
- **Gathering Nodes:** Map features (trees for wood, stone quarries, iron veins, hunting wildlife/farms) will expose harvestable capacity. Workers run behavior scripts or custom engine commands to extract resources.
- **Conversion to Engine Economy:** For compatibility with unit build costs, resources can either map into specialized engine storages or be validated authoritatively in synced gadgets prior to construction.

## 2. Gathering and Delivery
- **Work Cycles:** Villagers/workers travel from settlement hub or gather site to resource node, harvest until inventory threshold is met, and walk to the nearest warehouse/drop-off point.
- **Pathing:** Uses engine pathfinding with custom commands (`CMD_GATHER`, `CMD_DELIVER`) implemented via synced gadgets, ensuring interruption and ordinary move commands remain responsive.

## 3. Warehouses and Local Storage
- **Drop-off Points:** Town centers, granaries, lumber camps, and mining storehouses provide localized drop-off radiuses.
- **Logistics Buffers:** Storage capacities limit regional accumulation; goods must be hauled between hubs if local deficit occurs.

## 4. Roads and Logistics Connectivity
- **Road Networks:** Grid or spline-based road overlays that grant speed multipliers to units moving along established trade and hauling routes.
- **Connectivity Checks:** Synced graphs updated when road segments or buildings are placed, validating building access and supply lines.

## 5. Housing, Population, and Military Recruitment
- **Housing Cap:** Residential dwellings determine the maximum population ceiling.
- **Recruitment:** Military training requires idle population, food upkeep, and equipment (weapons/armor produced by smiths and fletchers) before initiating unit spawning.
