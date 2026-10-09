using UnrealBuildTool;

public class AndrewsAirsoftTarget : TargetRules
{
	public AndrewsAirsoftTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("AndrewsAirsoft");
	}
}
