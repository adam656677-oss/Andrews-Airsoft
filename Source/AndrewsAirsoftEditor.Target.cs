using UnrealBuildTool;

public class AndrewsAirsoftEditorTarget : TargetRules
{
	public AndrewsAirsoftEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("AndrewsAirsoft");
	}
}
