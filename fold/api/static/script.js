document.addEventListener('DOMContentLoaded', () => {
    // Encode Setup
    setupCard('encode');
    // Decode Setup
    setupCard('decode');
});

function setupCard(type) {
    const fileInput = document.getElementById(`${type}-file`);
    const uploadArea = document.getElementById(`${type}-upload`);
    const selectedFileDiv = document.getElementById(`${type}-selected`);
    const actionBtn = document.getElementById(`${type}-btn`);
    const statusDiv = document.getElementById(`${type}-status`);
    let currentFile = null;

    // File selection
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    // Drag and drop
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    function handleFileSelect(file) {
        currentFile = file;
        selectedFileDiv.textContent = `${file.name} (${formatBytes(file.size)})`;
        selectedFileDiv.classList.remove('hidden');
        actionBtn.disabled = false;
        statusDiv.textContent = '';
        statusDiv.className = 'status';
    }

    actionBtn.addEventListener('click', async () => {
        if (!currentFile) return;

        const formData = new FormData();
        formData.append('file', currentFile);

        actionBtn.disabled = true;
        statusDiv.textContent = `Processing...`;
        statusDiv.className = 'status loading';

        try {
            const response = await fetch(`/${type}`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => null);
                const errorText = errorData ? errorData.detail : await response.text();
                throw new Error(errorText || 'Process failed');
            }

            // Handle file download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            
            // Try to get filename from content-disposition
            let filename = '';
            const disposition = response.headers.get('content-disposition');
            if (disposition && disposition.indexOf('attachment') !== -1) {
                const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
                const matches = filenameRegex.exec(disposition);
                if (matches != null && matches[1]) { 
                    filename = matches[1].replace(/['"]/g, '');
                }
            }
            
            if (!filename) {
                filename = type === 'encode' ? `${currentFile.name}.avi` : `decoded_${currentFile.name}`;
            }

            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            statusDiv.textContent = `Success!`;
            statusDiv.className = 'status success';
        } catch (error) {
            statusDiv.textContent = `Error: ${error.message}`;
            statusDiv.className = 'status error';
        } finally {
            actionBtn.disabled = false;
        }
    });
}

function formatBytes(bytes, decimals = 2) {
    if (!+bytes) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}
