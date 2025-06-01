document.addEventListener('DOMContentLoaded', () => {
    // ... (deklarasi variabel yang sama seperti sebelumnya) ...
    const addTableBtn = document.getElementById('add-table-btn');
    const tablesContainer = document.getElementById('tables-container');
    const tableTemplate = document.getElementById('table-template');
    const columnTemplate = document.getElementById('column-template');
    const generateBtn = document.getElementById('generate-btn');
    const downloadLinksContainer = document.getElementById('download-links');
    const numRowsInput = document.getElementById('num-rows');

    const aiContextInput = document.getElementById('ai-context');
    const suggestSchemaBtn = document.getElementById('suggest-schema-btn');
    const aiStatus = document.getElementById('ai-status');

    document.getElementById('current-year').textContent = new Date().getFullYear();

    // --- Fungsi addTableToUI dan addColumnToTableUI SAMA SEPERTI SEBELUMNYA ---
    // --- (Salin dari versi lengkap sebelumnya) ---
    function updateColumnOptionsPlaceholder(columnTypeSelect, columnOptionsInput) {
        const type = columnTypeSelect.value;
        columnOptionsInput.style.display = 'inline-block';
        switch (type) {
            case 'string': columnOptionsInput.placeholder = "min_len=5,max_len=10"; break;
            case 'integer': case 'float': columnOptionsInput.placeholder = "min=0,max=100"; break;
            case 'date': columnOptionsInput.placeholder = "start=2020-01-01,end=today"; break;
            case 'custom_list': columnOptionsInput.placeholder = "item1,item2,item3"; break;
            case 'ai_text': columnOptionsInput.placeholder = "Additional instructions for AI (optional)"; break;
            default: columnOptionsInput.placeholder = "No specific options"; columnOptionsInput.style.display = 'none';
        }
    }
    function addColumnToTableUI(columnsContainer, columnData = {}) {
        const columnNode = columnTemplate.content.cloneNode(true);
        const columnNameInput = columnNode.querySelector('.column-name');
        const columnTypeSelect = columnNode.querySelector('.column-type');
        const columnOptionsInput = columnNode.querySelector('.column-options');
        const columnUniqueCheckbox = columnNode.querySelector('.column-unique');
        const columnNullableCheckbox = columnNode.querySelector('.column-nullable');
        const columnNullableChanceInput = columnNode.querySelector('.column-nullable-chance');
        const removeColumnBtn = columnNode.querySelector('.remove-column-btn');

        columnNameInput.value = columnData.name || '';
        columnTypeSelect.value = columnData.type || 'string';
        columnOptionsInput.value = columnData.options || '';
        columnUniqueCheckbox.checked = columnData.unique || false;
        columnNullableCheckbox.checked = columnData.nullable || false;
        columnNullableChanceInput.value = columnData.nullable_chance || 10;
        columnNullableChanceInput.style.display = columnNullableCheckbox.checked ? 'inline-block' : 'none';

        updateColumnOptionsPlaceholder(columnTypeSelect, columnOptionsInput);
        columnTypeSelect.addEventListener('change', () => updateColumnOptionsPlaceholder(columnTypeSelect, columnOptionsInput));
        columnNullableCheckbox.addEventListener('change', () => {
            columnNullableChanceInput.style.display = columnNullableCheckbox.checked ? 'inline-block' : 'none';
        });
        removeColumnBtn.addEventListener('click', (e) => e.target.closest('.column-definition').remove());
        columnsContainer.appendChild(columnNode);
    }
    function addTableToUI(name = '', columns = []) {
        const tableNode = tableTemplate.content.cloneNode(true);
        const tableNameInput = tableNode.querySelector('.table-name');
        const addColumnBtn = tableNode.querySelector('.add-column-btn');
        const removeTableBtn = tableNode.querySelector('.remove-table-btn');
        const columnsContainer = tableNode.querySelector('.columns-container');
        tableNameInput.value = name;
        addColumnBtn.addEventListener('click', () => addColumnToTableUI(columnsContainer));
        removeTableBtn.addEventListener('click', (e) => {
            e.target.closest('.table-definition').remove();
            if (tablesContainer.children.length === 0) addTableBtn.click();
        });
        if (columns.length > 0) columns.forEach(col => addColumnToTableUI(columnsContainer, col));
        else addColumnToTableUI(columnsContainer);
        tablesContainer.appendChild(tableNode);
    }
    addTableBtn.addEventListener('click', () => addTableToUI());
    // --- AKHIR FUNGSI UI HELPER ---


    // Event Listener untuk Saran Skema AI (SAMA SEPERTI SEBELUMNYA)
    suggestSchemaBtn.addEventListener('click', async () => {
        const context = aiContextInput.value.trim();
        if (!context) { alert("Please enter a description of the database context."); return; }
        aiStatus.textContent = "AI is thinking for schema suggestions... 🧠";
        suggestSchemaBtn.disabled = true;
        downloadLinksContainer.innerHTML = '';
        try {
            const response = await fetch('/suggest-schema-ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ context: context }),
            });
            if (!response.ok) { const err = await response.json(); throw new Error(err.error || `HTTP error! Status: ${response.status}`); }
            const suggestedSchema = await response.json();
            tablesContainer.innerHTML = ''; 
            if (suggestedSchema.tables && suggestedSchema.tables.length > 0) {
                suggestedSchema.tables.forEach(table => addTableToUI(table.name, table.columns));
                aiStatus.textContent = "Schema suggestions loaded successfully! Please review and adjust.";
            } else {
                aiStatus.textContent = "AI did not provide valid schema suggestions. Please try again.";
                addTableBtn.click();
            }
        } catch (error) {
            console.error('Error suggesting schema:', error);
            aiStatus.textContent = `Error saran skema: ${error.message}`;
            if (tablesContainer.children.length === 0) addTableBtn.click();
        } finally {
            suggestSchemaBtn.disabled = false;
        }
    });

    generateBtn.addEventListener('click', async () => {
        // BARU: Ambil format output yang dipilih
        const selectedOutputFormat = document.querySelector('input[name="outputFormat"]:checked')?.value || 'csv';

        const schema = {
            tables: [],
            num_rows: parseInt(numRowsInput.value) || 10,
            database_context: aiContextInput.value.trim() || "data umum",
            requested_format: selectedOutputFormat // BARU: Kirim format yang diminta
        };

        document.querySelectorAll('.table-definition').forEach(tableEl => {
            // ... (logika pengumpulan tabel dan kolom SAMA SEPERTI SEBELUMNYA) ...
            const tableName = tableEl.querySelector('.table-name').value.trim() || `TabelTanpaNama_${Date.now()}`;
            const tableData = { name: tableName, columns: [] };
            tableEl.querySelectorAll('.column-definition').forEach(colEl => {
                const columnName = colEl.querySelector('.column-name').value.trim() || `KolomTanpaNama_${Date.now()}`;
                tableData.columns.push({
                    name: columnName, type: colEl.querySelector('.column-type').value,
                    options: colEl.querySelector('.column-options').value.trim(),
                    unique: colEl.querySelector('.column-unique').checked,
                    nullable: colEl.querySelector('.column-nullable').checked,
                    nullable_chance: colEl.querySelector('.column-nullable').checked ? parseInt(colEl.querySelector('.column-nullable-chance').value) : 0
                });
            });
            if (tableData.columns.length > 0) schema.tables.push(tableData);
        });

        if (schema.tables.length === 0) { alert("Silakan definisikan setidaknya satu tabel dengan kolom."); return; }

        downloadLinksContainer.innerHTML = `<p>Memproses data (format: ${selectedOutputFormat.toUpperCase()})... Ini mungkin memakan waktu jika menggunakan Teks via AI.</p>`;
        generateBtn.disabled = true;

        try {
            const response = await fetch('/generate-data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(schema),
            });

            if (!response.ok) { const errorData = await response.json(); throw new Error(errorData.error || `HTTP error! status: ${response.status}`);}

            const result = await response.json();
            downloadLinksContainer.innerHTML = ''; 

            // BARU: Logika untuk menampilkan link download berdasarkan format yang dipilih
            if (result.download_info) {
                if (result.download_info.is_zip) {
                    // Handle ZIP file
                    const link = document.createElement('a');
                    link.href = result.download_info.url;
                    link.textContent = `Unduh Semua Tabel (${result.download_info.format.toUpperCase()}) - ZIP`;
                    link.download = result.download_info.filename; // Nama file dari backend
                    downloadLinksContainer.appendChild(link);
                } else if (result.download_info.files && result.download_info.files.length > 0) {
                    // Handle individual files
                    result.download_info.files.forEach(file => {
                        const link = document.createElement('a');
                        link.href = file.url;
                        link.textContent = `Unduh ${file.table_name}.${file.format}`;
                        link.download = file.filename; // Nama file dari backend
                        downloadLinksContainer.appendChild(link);
                        downloadLinksContainer.appendChild(document.createElement('br'));
                    });
                } else {
                     downloadLinksContainer.innerHTML = '<p>Tidak ada file yang dihasilkan atau respons tidak dikenal.</p>';
                }
            } else {
                downloadLinksContainer.innerHTML = '<p>Tidak ada informasi download yang diterima dari server.</p>';
            }

        } catch (error) {
            console.error('Error generating data:', error);
            downloadLinksContainer.innerHTML = `<p>Error generate data: ${error.message}</p>`;
        } finally {
            generateBtn.disabled = false;
        }
    });

    if (tablesContainer.children.length === 0) {
        addTableBtn.click();
    }
});