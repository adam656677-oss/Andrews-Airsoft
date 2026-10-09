using UnrealBuildTool;

public class AndrewsAirsoft : ModuleRules
{
	public AndrewsAirsoft(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"Slate",
			"SlateCore",
			"UMG",
			"Json",
			"JsonUtilities",
			"NetCore",
			"PhysicsCore",
			"DeveloperSettings",
			"AudioMixer"
		});
	}
}
