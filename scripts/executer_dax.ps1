# Exécute les requêtes DAX de powerbi/controles/ sur le modèle ouvert dans Power BI Desktop
# et écrit les résultats dans results/powerbi/*.csv.
#
# Pré-requis : le projet powerbi/DVF-Herault.pbip est ouvert dans Power BI Desktop et actualisé.
# Le moteur local (msmdsrv.exe) écoute sur un port dynamique, retrouvé ici par le processus.
#
# Usage (PowerShell, depuis la racine du dépôt) : .\scripts\executer_dax.ps1

$racine = Split-Path -Parent $PSScriptRoot
$sortie = Join-Path $racine "results\powerbi"
New-Item -ItemType Directory -Force -Path $sortie | Out-Null

$bin = (Get-AppxPackage -Name Microsoft.MicrosoftPowerBIDesktop).InstallLocation + "\bin"
if (-not (Test-Path "$bin\Microsoft.PowerBI.AdomdClient.dll")) {
    throw "Client ADOMD introuvable : Power BI Desktop (version Microsoft Store) n'est pas installé."
}
Add-Type -Path "$bin\Microsoft.PowerBI.AdomdClient.dll"

$moteur = Get-Process msmdsrv -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $moteur) { throw "Aucun moteur Analysis Services : ouvrir powerbi/DVF-Herault.pbip dans Power BI Desktop." }
$port = (Get-NetTCPConnection -OwningProcess $moteur.Id |
         Where-Object { $_.State -eq "Listen" -and $_.LocalAddress -eq "127.0.0.1" } |
         Select-Object -First 1).LocalPort

$connexion = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port")
$connexion.Open()
Write-Output "Modèle : $($connexion.Database.Name) (port $port)"

foreach ($requete in Get-ChildItem (Join-Path $racine "powerbi\controles") -Filter "*.dax" | Sort-Object Name) {
    $commande = $connexion.CreateCommand()
    $commande.CommandText = Get-Content -Raw -Encoding UTF8 $requete.FullName
    # L'adaptateur remplit la table sans appliquer de contraintes : certaines mesures renvoient BLANK.
    $adaptateur = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdDataAdapter($commande)
    $table = New-Object System.Data.DataTable
    $adaptateur.Fill($table) | Out-Null
    $cible = Join-Path $sortie ($requete.BaseName + ".csv")
    $table | Export-Csv -Path $cible -NoTypeInformation -Encoding UTF8
    Write-Output "$($requete.Name) : $($table.Rows.Count) lignes -> results/powerbi/$($requete.BaseName).csv"
}
$connexion.Close()
