# Local integration only. No third-party binaries are bundled by this project.
param(
 [Parameter(Mandatory=$true)][string]$IntegratorExe,
 [Parameter(Mandatory=$true)][string]$CecilDll,
 [string]$ProfileDirectory=(Join-Path $PSScriptRoot '..\.work\build')
)
$ErrorActionPreference='Stop'
$IntegratorExe=(Resolve-Path -LiteralPath $IntegratorExe).Path
$CecilDll=(Resolve-Path -LiteralPath $CecilDll).Path
$ProfileDirectory=(Resolve-Path -LiteralPath $ProfileDirectory).Path
$versions=Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\profile\tool-versions.json') -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $IntegratorExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $versions.mod_integrator.sha256){throw 'Mod manager version differs from the pinned tool'}
if((Get-FileHash -LiteralPath $CecilDll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $versions.mono_cecil.sha256){throw 'Mono.Cecil version differs from the pinned tool (use lib/net40)'}
if(!(Test-Path -LiteralPath (Join-Path $ProfileDirectory 'profile.json'))){throw 'Run profile.py prepare first'}
if(Test-Path -LiteralPath (Join-Path $ProfileDirectory 'local-integrator')){throw 'Use a fresh build folder; a local integrator already exists'}
$toolRoot=Join-Path $ProfileDirectory 'integration-inputs'
[void][IO.Directory]::CreateDirectory($toolRoot)
Copy-Item -LiteralPath $IntegratorExe -Destination (Join-Path $toolRoot 'ModIntegrator.exe')
# Extract only dependency DLL resources from the user-supplied official tool.
# Keep every extracted or modified file in the ignored local build directory.
[void][Reflection.Assembly]::LoadFrom($CecilDll)
$resourceAssembly=[Mono.Cecil.AssemblyDefinition]::ReadAssembly($IntegratorExe)
try{
 foreach($resource in $resourceAssembly.MainModule.Resources){
  if($resource -is [Mono.Cecil.EmbeddedResource] -and $resource.Name.EndsWith('.dll')){
   [IO.File]::WriteAllBytes((Join-Path $toolRoot ([IO.Path]::GetFileName($resource.Name))),$resource.GetResourceData())
  }
 }
}finally{$resourceAssembly.Dispose()}
if((Get-FileHash -LiteralPath (Join-Path $toolRoot 'AssetParser.dll') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $versions.asset_parser_sha256){throw 'Unexpected embedded AssetParser'}
Add-Type -AssemblyName PresentationCore,PresentationFramework,WindowsBase

[void][Reflection.Assembly]::LoadFrom($CecilDll)
$resolver=[Mono.Cecil.DefaultAssemblyResolver]::new();$resolver.AddSearchDirectory($toolRoot)
$parameters=[Mono.Cecil.ReaderParameters]::new();$parameters.AssemblyResolver=$resolver
$assembly=[Mono.Cecil.AssemblyDefinition]::ReadAssembly((Join-Path $toolRoot 'ModIntegrator.exe'),$parameters)
$module=$assembly.MainModule
$consoleType=[Mono.Cecil.TypeReference]::new('System','Console',$module,$module.TypeSystem.Object.Scope)
$writeLine=[Mono.Cecil.MethodReference]::new('WriteLine',$module.TypeSystem.Void,$consoleType)
$writeLine.Parameters.Add([Mono.Cecil.ParameterDefinition]::new($module.TypeSystem.String))
$changed=0
function Patch-Type($type) {
 foreach($method in $type.Methods) {
  if(!$method.HasBody){continue}
  $il=$method.Body.GetILProcessor()
  foreach($instruction in @($method.Body.Instructions)) {
   if($instruction.Operand -is [Mono.Cecil.MethodReference] -and $instruction.Operand.DeclaringType.FullName -eq 'System.Windows.MessageBox' -and $instruction.Operand.Name -eq 'Show') {
    $count=$instruction.Operand.Parameters.Count
    if($count -eq 1){$instruction.OpCode=[Mono.Cecil.Cil.OpCodes]::Call;$instruction.Operand=$writeLine}
    else {
     $instruction.OpCode=[Mono.Cecil.Cil.OpCodes]::Pop;$instruction.Operand=$null
     $cursor=$instruction
     for($n=1;$n -lt $count;$n++){$next=$il.Create([Mono.Cecil.Cil.OpCodes]::Pop);$il.InsertAfter($cursor,$next);$cursor=$next}
     $il.InsertAfter($cursor,$il.Create([Mono.Cecil.Cil.OpCodes]::Ldc_I4_0));$script:changed++;continue
    }
    $il.InsertAfter($instruction,$il.Create([Mono.Cecil.Cil.OpCodes]::Ldc_I4_0));$script:changed++
   }
  }
  if($type.FullName -eq 'ModIntegrator.CoreClass' -and $method.Name -eq 'BuildMod') {
   $method.Body.ExceptionHandlers.Clear();$method.Body.Variables.Clear();$method.Body.Instructions.Clear()
   $il.Append($il.Create([Mono.Cecil.Cil.OpCodes]::Ldnull));$il.Append($il.Create([Mono.Cecil.Cil.OpCodes]::Ret))
  }
 }
 foreach($nested in $type.NestedTypes){Patch-Type $nested}
}
foreach($type in $module.Types){Patch-Type $type}
$dest=Join-Path $ProfileDirectory 'local-integrator';[IO.Directory]::CreateDirectory($dest)|Out-Null
$assembly.Write((Join-Path $dest 'ModIntegrator.exe'));$assembly.Dispose()
Copy-Item -LiteralPath (Join-Path $toolRoot 'AssetParser.dll') -Destination $dest
foreach($dll in Get-ChildItem -LiteralPath $toolRoot -Filter '*.dll'){Copy-Item -LiteralPath $dll.FullName -Destination $dest -Force}
"Patched $changed message-box calls to console output. GUI entrypoint will not be executed."

$toolRoot=$dest
foreach($file in Get-ChildItem -LiteralPath $toolRoot -Filter '*.dll') {try{[void][Reflection.Assembly]::LoadFrom($file.FullName)}catch{}}
$asm=[Reflection.Assembly]::LoadFrom((Join-Path $toolRoot 'ModIntegrator.exe'))
$asm.GetType('ModIntegrator.EmbeddedLibsResolver').GetMethod('Init',[Reflection.BindingFlags]'Public,NonPublic,Static').Invoke($null,@())
$coreType=$asm.GetType('ModIntegrator.CoreClass')
$core=[Runtime.Serialization.FormatterServices]::GetUninitializedObject($coreType)
$pakType=$asm.GetType('ModIntegrator.PakMod')
$metaType=$asm.GetType('ModIntegrator.MetaData')
$collectionType=[System.Collections.ObjectModel.ObservableCollection`1].MakeGenericType([Type[]]@($pakType))
$mods=[Activator]::CreateInstance($collectionType)
$records=Get-Content -LiteralPath (Join-Path $ProfileDirectory 'profile.json') -Raw|ConvertFrom-Json
foreach($record in $records) {
 $mod=[Runtime.Serialization.FormatterServices]::GetUninitializedObject($pakType)
 $meta=[Activator]::CreateInstance($metaType)
 foreach($prop in $record.metadata.PSObject.Properties){
  $target=$metaType.GetProperty($prop.Name)
  if($null -eq $target){continue}
  $value=$prop.Value
  if($null -ne $value) {
   if($target.PropertyType -eq [string[]]){$value=[string[]]@($value)}
   elseif($target.PropertyType -eq [string[][]]){$value=[string[][]]@($value|ForEach-Object {,[string[]]$_})}
  }
  $target.SetValue($meta,$value,$null)
 }
 $pakType.GetProperty('MetaInfo').SetValue($mod,$meta,$null)
 $enabled=$pakType.GetField('isenabled',[Reflection.BindingFlags]'NonPublic,Public,Instance')
 $enabled.SetValue($mod,$true)
 $pak=[Runtime.Serialization.FormatterServices]::GetUninitializedObject([AssetParser.Pak])
 $pak.Contents=[AssetParser.UAsset[]]@()
 $pakType.GetField('Data',[Reflection.BindingFlags]'Public,NonPublic,Instance').SetValue($mod,$pak)
 $mods.Add($mod)
}
$coreType.GetField('<InstalledMods>k__BackingField',[Reflection.BindingFlags]'NonPublic,Instance').SetValue($core,$mods)
$dir=(Join-Path $ProfileDirectory 'Paks')+'\'
$coreType.GetField('<CurrentPakDirectory>k__BackingField',[Reflection.BindingFlags]'NonPublic,Instance').SetValue($core,$dir)
$method=$coreType.GetMethod('CreateIntegration',[Reflection.BindingFlags]'Public,NonPublic,Instance')
$method.Invoke($core,[object[]]@(''))
if(!(Test-Path -LiteralPath (Join-Path $dir '000-0ModIntegration_P.pak'))){throw 'Integration did not produce a PAK'}
Get-Item -LiteralPath (Join-Path $dir '000-0ModIntegration_P.pak') | Select-Object Name,Length
