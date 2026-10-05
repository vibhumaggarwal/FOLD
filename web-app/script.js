// FOLD Frontend Engine
// Core Logic for File <-> Video Steganography

// ------------------------------------------------------------------
// UTILITIES
// ------------------------------------------------------------------
const formatBytes = (bytes, decimals = 2) => {
    if (!+bytes) return '0 B';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
};

const showToast = (message, type = 'success') => {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        if(toast.parentElement) toast.remove();
    }, 4500); // Wait for fade out
};

// CRC32 Implementation
const makeCRCTable = () => {
    let c;
    const crcTable = [];
    for (let n = 0; n < 256; n++) {
        c = n;
        for (let k = 0; k < 8; k++) c = ((c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1));
        crcTable[n] = c;
    }
    return crcTable;
};
const crcTable = makeCRCTable();

const calcCRC32 = (buffer) => {
    let crc = 0 ^ (-1);
    for (let i = 0; i < buffer.byteLength; i++) {
        crc = (crc >>> 8) ^ crcTable[(crc ^ buffer[i]) & 0xFF];
    }
    return (crc ^ (-1)) >>> 0;
};

// ------------------------------------------------------------------
// UI STATE & TABS
// ------------------------------------------------------------------
const tabs = document.querySelectorAll('.tab-button');
const panels = document.querySelectorAll('.panel');

tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        panels.forEach(p => p.classList.remove('active'));
        
        tab.classList.add('active');
        document.getElementById(tab.dataset.target).classList.add('active');
    });
});

const setupDropZone = (type) => {
    const dropZone = document.getElementById(`${type}-drop`);
    const input = document.getElementById(`${type}-input`);
    const fileInfo = document.getElementById(`${type}-file-info`);
    const filenameLabel = document.getElementById(`${type}-filename`);
    const filesizeLabel = document.getElementById(`${type}-filesize`);
    const removeBtn = document.getElementById(`${type}-remove`);
    const actionBtn = document.getElementById(`${type}-btn`);
    
    let currentFile = null;

    dropZone.addEventListener('click', () => input.click());
    input.addEventListener('change', (e) => handleFile(e.target.files[0]));

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    ['dragleave', 'drop'].forEach(evt => {
        dropZone.addEventListener(evt, (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (evt === 'drop' && e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
        });
    });

    const handleFile = (file) => {
        if (!file) return;
        currentFile = file;
        window[`${type}File`] = file;
        
        filenameLabel.textContent = file.name;
        filesizeLabel.textContent = formatBytes(file.size);
        dropZone.style.display = 'none';
        fileInfo.classList.remove('hidden');
        actionBtn.disabled = false;
    };

    removeBtn.addEventListener('click', () => {
        currentFile = null;
        window[`${type}File`] = null;
        input.value = '';
        dropZone.style.display = 'block';
        fileInfo.classList.add('hidden');
        actionBtn.disabled = true;
        
        // Hide preview areas
        document.getElementById(`${type}-preview-area`).classList.add('hidden');
    });
};

setupDropZone('encode');
setupDropZone('decode');


// ------------------------------------------------------------------
// CONSTANTS
// ------------------------------------------------------------------
const CANVAS_SIZE = 512;
const BLOCK_SIZE = 4;
const GRID_SIZE = CANVAS_SIZE / BLOCK_SIZE; // 128
const BITS_PER_FRAME = GRID_SIZE * GRID_SIZE; // 16,384

const FRAME_INDEX_BITS = 32;
const PAYLOAD_LEN_BITS = 16;
const HEADER_BITS = FRAME_INDEX_BITS + PAYLOAD_LEN_BITS; // 48
const MAX_PAYLOAD_BITS = BITS_PER_FRAME - HEADER_BITS; // 16,336


// ------------------------------------------------------------------
// ENCODER LOGIC
// ------------------------------------------------------------------
const encodeBtn = document.getElementById('encode-btn');
encodeBtn.addEventListener('click', async () => {
    const file = window.encodeFile;
    if (!file) return;

    // UI Prep
    encodeBtn.disabled = true;
    encodeBtn.querySelector('.btn-loader').classList.remove('hidden');
    encodeBtn.querySelector('.btn-text').textContent = 'ENCODING...';
    
    const previewArea = document.getElementById('encode-preview-area');
    const progressBar = document.getElementById('encode-progress');
    const statusText = document.getElementById('encode-status');
    const canvas = document.getElementById('encode-canvas');
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    
    previewArea.classList.remove('hidden');
    progressBar.style.width = '0%';
    statusText.textContent = 'Reading file bytes...';

    try {
        // 1. Read file
        const arrayBuffer = await file.arrayBuffer();
        const fileBytes = new Uint8Array(arrayBuffer);
        const crc = calcCRC32(fileBytes);
        
        // 2. Construct FOLD Header
        // MAGIC (4), NameLen (1), Name (N), FileLen (4), CRC32 (4)
        const nameBytes = new TextEncoder().encode(file.name);
        const nameLen = Math.min(nameBytes.length, 255);
        const headerSize = 4 + 1 + nameLen + 4 + 4;
        
        const fullBytes = new Uint8Array(headerSize + fileBytes.length);
        
        // MAGIC "FOLD"
        fullBytes.set([70, 79, 76, 68], 0);
        // NameLen
        fullBytes[4] = nameLen;
        // Name
        fullBytes.set(nameBytes.slice(0, nameLen), 5);
        
        // FileLen (4 bytes)
        const view = new DataView(fullBytes.buffer);
        view.setUint32(5 + nameLen, fileBytes.length, false); // big-endian
        
        // CRC32 (4 bytes)
        view.setUint32(9 + nameLen, crc, false); // big-endian
        
        // Data payload
        fullBytes.set(fileBytes, 13 + nameLen);
        
        // 3. Convert all bytes to a giant Bit Array (represented as Uint8Array of 1s and 0s)
        statusText.textContent = 'Compiling bit sequence...';
        const totalBits = fullBytes.length * 8;
        const allBits = new Uint8Array(totalBits);
        let bitOffset = 0;
        for (let i = 0; i < fullBytes.length; i++) {
            const b = fullBytes[i];
            allBits[bitOffset++] = (b >> 7) & 1;
            allBits[bitOffset++] = (b >> 6) & 1;
            allBits[bitOffset++] = (b >> 5) & 1;
            allBits[bitOffset++] = (b >> 4) & 1;
            allBits[bitOffset++] = (b >> 3) & 1;
            allBits[bitOffset++] = (b >> 2) & 1;
            allBits[bitOffset++] = (b >> 1) & 1;
            allBits[bitOffset++] = b & 1;
        }

        // 4. Setup MediaRecorder
        statusText.textContent = 'Recording fractal sequence...';
        
        // We set Framerate to explicitly handle timing, 30fps stream.
        const stream = canvas.captureStream(30); 
        const recorderOptions = { mimeType: 'video/webm' };
        if (MediaRecorder.isTypeSupported('video/webm;codecs=vp9')) {
            recorderOptions.mimeType = 'video/webm;codecs=vp9';
            recorderOptions.videoBitsPerSecond = 5000000; // 5 Mbps to ensure clean blocks
        }
        
        const mediaRecorder = new MediaRecorder(stream, recorderOptions);
        const chunks = [];
        mediaRecorder.ondataavailable = e => chunks.push(e.data);
        
        const recordingDone = new Promise(resolve => mediaRecorder.onstop = resolve);
        mediaRecorder.start();

        // 5. Draw frames
        const totalFrames = Math.ceil(totalBits / MAX_PAYLOAD_BITS);
        let currentFrame = 0;
        let globalBitIndex = 0;
        
        // Draw black background initially
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

        for (let frameIdx = 0; frameIdx < totalFrames; frameIdx++) {
            const frameImgData = ctx.createImageData(CANVAS_SIZE, CANVAS_SIZE);
            const data = frameImgData.data;
            
            // Frame bits setup
            const bitsLeft = totalBits - globalBitIndex;
            const payloadLen = Math.min(bitsLeft, MAX_PAYLOAD_BITS);
            
            // Generate single frame bits sequence
            const frameBits = new Uint8Array(BITS_PER_FRAME);
            
            // Embed Frame Index (32 bits)
            for (let i = 0; i < 32; i++) {
                frameBits[i] = (frameIdx >> (31 - i)) & 1;
            }
            // Embed Payload Length (16 bits)
            for (let i = 0; i < 16; i++) {
                frameBits[32 + i] = (payloadLen >> (15 - i)) & 1;
            }
            // Embed Data
            for (let i = 0; i < payloadLen; i++) {
                frameBits[48 + i] = allBits[globalBitIndex++];
            }
            
            // Render 128x128 grid -> 512x512 pixels
            let fbIndex = 0;
            for (let y = 0; y < GRID_SIZE; y++) {
                for (let x = 0; x < GRID_SIZE; x++) {
                    const val = frameBits[fbIndex++] ? 255 : 0;
                    
                    // 4x4 block offset
                    const startY = y * BLOCK_SIZE;
                    const startX = x * BLOCK_SIZE;
                    
                    for (let by = 0; by < BLOCK_SIZE; by++) {
                        for (let bx = 0; bx < BLOCK_SIZE; bx++) {
                            const idx = ((startY + by) * CANVAS_SIZE + (startX + bx)) * 4;
                            data[idx] = val;
                            data[idx+1] = val;
                            data[idx+2] = val;
                            data[idx+3] = 255;
                        }
                    }
                }
            }
            
            ctx.putImageData(frameImgData, 0, 0);
            progressBar.style.width = `${((frameIdx + 1) / totalFrames) * 100}%`;
            
            // Force stream to capture this frame. Awaiting 100ms guarantees the stream captures it exactly as it is, 
            // since 30fps is ~33ms, 100ms means each frame gets recorded 3-4 times in the video!
            // The decoder's frame index check will ignore the duplicates.
            await new Promise(r => setTimeout(r, 100));
        }
        
        // Finalize
        mediaRecorder.stop();
        statusText.textContent = 'Processing video format...';
        await recordingDone;
        
        const blob = new Blob(chunks, { type: 'video/webm' });
        const url = URL.createObjectURL(blob);
        
        // Trigger download
        const a = document.createElement('a');
        a.href = url;
        a.download = `fold_${file.name}.webm`;
        a.click();
        URL.revokeObjectURL(url);
        
        showToast('Sequence encoded and exported successfully!', 'success');
        statusText.textContent = 'Ready.';
        
    } catch (err) {
        console.error(err);
        showToast('Encoding Error: ' + err.message, 'error');
        statusText.textContent = 'Failed.';
    } finally {
        encodeBtn.disabled = false;
        encodeBtn.querySelector('.btn-loader').classList.add('hidden');
        encodeBtn.querySelector('.btn-text').textContent = 'INITIALIZE ENCODING';
    }
});


// ------------------------------------------------------------------
// DECODER LOGIC
// ------------------------------------------------------------------
const decodeBtn = document.getElementById('decode-btn');
decodeBtn.addEventListener('click', async () => {
    const file = window.decodeFile;
    if (!file) return;

    // UI Prep
    decodeBtn.disabled = true;
    decodeBtn.querySelector('.btn-loader').classList.remove('hidden');
    decodeBtn.querySelector('.btn-text').textContent = 'EXTRACTING...';
    
    const previewArea = document.getElementById('decode-preview-area');
    const progressBar = document.getElementById('decode-progress');
    const statusText = document.getElementById('decode-status');
    const canvas = document.getElementById('decode-canvas');
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const video = document.getElementById('decode-video');
    
    previewArea.classList.remove('hidden');
    progressBar.style.width = '0%';
    statusText.textContent = 'Mounting media source...';

    const objectUrl = URL.createObjectURL(file);
    video.src = objectUrl;
    
    await new Promise(r => {
        video.onloadeddata = r;
    });

    statusText.textContent = 'Scanning frames...';
    
    // Every copy of a frame votes on each bit (frames are recorded several times),
    // and frames are keyed by their embedded index so dropped or repeated frames are harmless.
    const votes = new Map();   // frameIdx -> Float32Array of summed block brightness
    const counts = new Map();  // frameIdx -> number of copies seen
    let finished = false;

    const readHeader = (levels) => {
        let frameIdx = 0, payloadLen = 0;
        for (let i = 0; i < FRAME_INDEX_BITS; i++) frameIdx = frameIdx * 2 + (levels[i] > 127 ? 1 : 0);
        for (let i = FRAME_INDEX_BITS; i < HEADER_BITS; i++) payloadLen = payloadLen * 2 + (levels[i] > 127 ? 1 : 0);
        return { frameIdx, payloadLen };
    };
    
    const processFrame = (now, metadata) => {
        if (finished) return;
        // Draw current video frame to canvas to read pixels
        ctx.drawImage(video, 0, 0, CANVAS_SIZE, CANVAS_SIZE);
        const imgData = ctx.getImageData(0, 0, CANVAS_SIZE, CANVAS_SIZE).data;
        
        // Average brightness of each whole 4x4 block, which is far more robust
        // to compression than sampling a single pixel
        const levels = new Float32Array(BITS_PER_FRAME);
        let fbIndex = 0;
        for (let y = 0; y < GRID_SIZE; y++) {
            for (let x = 0; x < GRID_SIZE; x++) {
                let sum = 0;
                for (let by = 0; by < BLOCK_SIZE; by++) {
                    let pxIdx = ((y * BLOCK_SIZE + by) * CANVAS_SIZE + x * BLOCK_SIZE) * 4;
                    for (let bx = 0; bx < BLOCK_SIZE; bx++, pxIdx += 4) {
                        sum += imgData[pxIdx] + imgData[pxIdx + 1] + imgData[pxIdx + 2];
                    }
                }
                levels[fbIndex++] = sum / (BLOCK_SIZE * BLOCK_SIZE * 3);
            }
        }
        
        const { frameIdx, payloadLen } = readHeader(levels);
        // Ignore frames whose header is clearly damaged
        if (payloadLen <= MAX_PAYLOAD_BITS && frameIdx < 10000000) {
            if (votes.has(frameIdx)) {
                const acc = votes.get(frameIdx);
                for (let i = 0; i < BITS_PER_FRAME; i++) acc[i] += levels[i];
                counts.set(frameIdx, counts.get(frameIdx) + 1);
            } else {
                votes.set(frameIdx, levels);
                counts.set(frameIdx, 1);
            }
        }
        progressBar.style.width = `${Math.min(100, (video.currentTime / video.duration) * 100)}%`;
        statusText.textContent = `Scanning frames... ${votes.size} found`;
        
        if (!video.ended) video.requestVideoFrameCallback(processFrame);
    };

    const assembleBits = () => {
        if (votes.size === 0) throw new Error("No FOLD frames found in this video.");
        const last = Math.max(...votes.keys());
        const missing = [];
        for (let i = 0; i <= last; i++) if (!votes.has(i)) missing.push(i);
        if (missing.length) {
            throw new Error(`${missing.length} frame(s) missing (index ${missing.slice(0, 5).join(', ')}${missing.length > 5 ? '…' : ''}). Try decoding again with this tab in the foreground.`);
        }
        const bits = [];
        for (let i = 0; i <= last; i++) {
            const acc = votes.get(i), n = counts.get(i);
            const levels = acc.map(v => v / n);
            const { payloadLen } = readHeader(levels);
            for (let j = 0; j < payloadLen; j++) bits.push(levels[HEADER_BITS + j] > 127 ? 1 : 0);
        }
        return bits;
    };
    
    const finalizeDecoding = () => {
        if (finished) return;
        finished = true;
        statusText.textContent = 'Reconstructing byte arrays...';
        URL.revokeObjectURL(objectUrl);
        
        try {
            const completePayloadBits = assembleBits();
            // Group bits into bytes
            const totalBytes = Math.floor(completePayloadBits.length / 8);
            const fullBytes = new Uint8Array(totalBytes);
            for (let i = 0; i < totalBytes; i++) {
                let b = 0;
                b |= completePayloadBits[i*8 + 0] << 7;
                b |= completePayloadBits[i*8 + 1] << 6;
                b |= completePayloadBits[i*8 + 2] << 5;
                b |= completePayloadBits[i*8 + 3] << 4;
                b |= completePayloadBits[i*8 + 4] << 3;
                b |= completePayloadBits[i*8 + 5] << 2;
                b |= completePayloadBits[i*8 + 6] << 1;
                b |= completePayloadBits[i*8 + 7];
                fullBytes[i] = b;
            }
            
            // Check MAGIC FOLD
            if (fullBytes[0] !== 70 || fullBytes[1] !== 79 || fullBytes[2] !== 76 || fullBytes[3] !== 68) {
                throw new Error("Invalid FOLD signature found. Lossless .avi/.mkv videos can only be decoded with the Python tool; the browser reads robust .webm/.mp4 videos.");
            }
            
            const nameLen = fullBytes[4];
            const nameBytes = fullBytes.slice(5, 5 + nameLen);
            const originalFilename = new TextDecoder().decode(nameBytes);
            
            const view = new DataView(fullBytes.buffer);
            const fileLen = view.getUint32(5 + nameLen, false);
            const crcExpected = view.getUint32(9 + nameLen, false);
            
            const headerEnd = 13 + nameLen;
            if (fullBytes.length < headerEnd + fileLen) {
                throw new Error("Video ended before all data was recovered.");
            }
            const fileData = fullBytes.slice(headerEnd, headerEnd + fileLen);
            
            // Verify Integrity
            const crcActual = calcCRC32(fileData);
            if (crcActual !== crcExpected) {
                throw new Error(`CRC32 Checksum Failed! Expected: ${crcExpected}, Got: ${crcActual}`);
            }
            
            // Trigger Download
            const blob = new Blob([fileData]);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = originalFilename || 'decoded_file.bin';
            a.click();
            URL.revokeObjectURL(url);
            
            progressBar.style.width = '100%';
            statusText.textContent = `Success: Recovered ${originalFilename}`;
            showToast('Decoded successfully and integrity verified.', 'success');
            
        } catch(err) {
            console.error(err);
            statusText.textContent = 'Decoding Error.';
            showToast(err.message, 'error');
        } finally {
            decodeBtn.disabled = false;
            decodeBtn.querySelector('.btn-loader').classList.add('hidden');
            decodeBtn.querySelector('.btn-text').textContent = 'EXTRACT DATA';
        }
    };
    
    // The last frame's callback can fire before 'ended', so finish on 'ended' too
    video.onended = () => setTimeout(finalizeDecoding, 50);
    video.onerror = () => {
        showToast('This browser cannot play that video file.', 'error');
        finished = true;
        decodeBtn.disabled = false;
        decodeBtn.querySelector('.btn-loader').classList.add('hidden');
        decodeBtn.querySelector('.btn-text').textContent = 'EXTRACT DATA';
    };

    // Start video playback silently
    video.currentTime = 0;
    video.requestVideoFrameCallback(processFrame);
    video.play().catch(err => {
        video.onerror();
        console.error(err);
    });
});
