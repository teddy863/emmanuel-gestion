function openOfflineDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("EmmanuelOfflineDB", 1);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains("ventes_attente")) {
        db.createObjectStore("ventes_attente", { keyPath: "id", autoIncrement: true });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = (e) => reject(e);
  });
}

async function sauvegarderVenteLocalement(venteData) {
  const db = await openOfflineDB();
  const tx = db.transaction("ventes_attente", "readwrite");
  tx.objectStore("ventes_attente").add({ ...venteData, timestamp: new Date().toISOString() });
  alert("Coupure réseau : Vente enregistrée en mémoire locale. Synchronisation automatique dès le retour d'Internet.");
}

async function synchroniserVentesEnAttente() {
  if (!navigator.onLine) return;
  const db = await openOfflineDB();
  const tx = db.transaction("ventes_attente", "readwrite");
  const store = tx.objectStore("ventes_attente");
  const request = store.getAll();

  request.onsuccess = async () => {
    const ventes = request.result;
    if (!ventes.length) return;

    for (const vente of ventes) {
      try {
        const response = await fetch(vente.endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams(vente.payload)
        });
        if (response.ok) {
          const deleteTx = db.transaction("ventes_attente", "readwrite");
          deleteTx.objectStore("ventes_attente").delete(vente.id);
        }
      } catch (err) {
        console.error("Erreur synchro :", err);
      }
    }
  };
}

window.addEventListener('online', synchroniserVentesEnAttente);