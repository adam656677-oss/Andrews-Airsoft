#include "AirsoftSettings.h"

FAirsoftBotTuning FAirsoftBotTuning::Preset(EAirsoftBotSkill Skill)
{
	// Normal is the struct's defaults; the others scale reaction, accuracy, awareness and nerve.
	FAirsoftBotTuning T;
	switch (Skill)
	{
	case EAirsoftBotSkill::Easy:
		T.ReactionTime = 0.75f;   T.ReactionPer10m = 0.1f;
		T.SightRange = 3500.f;    T.ViewHalfAngle = 55.f;   T.SightInterval = 0.3f;
		T.AimErrorStart = 9.f;    T.AimErrorMin = 1.6f;     T.AimSettleRate = 1.f;
		T.TargetMoveError = 0.7f; T.SelfMoveError = 2.5f;   T.LeadSkill = 0.2f;
		T.TurnRate = 220.f;       T.TriggerDiscipline = 2.6f; T.TapInterval = 0.5f;
		T.BurstMin = 2;           T.BurstMax = 4;           T.BurstPause = 0.6f;
		T.CrouchChance = 0.1f;    T.StrafeChance = 0.2f;    T.MemoryTime = 4.f;
		T.GrenadeChance = 0.1f;   T.HearingScale = 0.7f;
		break;
	case EAirsoftBotSkill::Hard:
		T.ReactionTime = 0.33f;   T.ReactionPer10m = 0.05f;
		T.SightRange = 6500.f;    T.ViewHalfAngle = 75.f;   T.SightInterval = 0.16f;
		T.AimErrorStart = 4.f;    T.AimErrorMin = 0.5f;     T.AimSettleRate = 2.4f;
		T.TargetMoveError = 0.25f; T.SelfMoveError = 1.f;   T.LeadSkill = 0.8f;
		T.TurnRate = 450.f;       T.TriggerDiscipline = 1.4f; T.TapInterval = 0.22f;
		T.BurstMin = 4;           T.BurstMax = 7;           T.BurstPause = 0.28f;
		T.CrouchChance = 0.35f;   T.StrafeChance = 0.55f;   T.MemoryTime = 8.f;
		T.GrenadeChance = 0.4f;   T.HearingScale = 1.15f;
		break;
	case EAirsoftBotSkill::Expert:
		T.ReactionTime = 0.22f;   T.ReactionPer10m = 0.03f;
		T.SightRange = 8000.f;    T.ViewHalfAngle = 85.f;   T.SightInterval = 0.12f;
		T.AimErrorStart = 2.5f;   T.AimErrorMin = 0.25f;    T.AimSettleRate = 3.4f;
		T.TargetMoveError = 0.15f; T.SelfMoveError = 0.6f;  T.LeadSkill = 0.95f;
		T.TurnRate = 600.f;       T.TriggerDiscipline = 1.1f; T.TapInterval = 0.15f;
		T.BurstMin = 4;           T.BurstMax = 8;           T.BurstPause = 0.2f;
		T.CrouchChance = 0.4f;    T.StrafeChance = 0.65f;   T.MemoryTime = 10.f;
		T.GrenadeChance = 0.55f;  T.HearingScale = 1.3f;
		break;
	default:
		break;
	}
	return T;
}
