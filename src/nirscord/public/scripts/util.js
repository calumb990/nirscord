export function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

export function choice(array) {
    return array[Math.floor(Math.random() * array.length)];
}

/**
 * 
 * @param {(args) => Promise<any>} callback 
 */
export function lock(callback) {
    let locked = false;

    return async args => {
        if (locked) return;

        // Lock the thread
        locked = true;
        await callback(args);
        locked = false;
    }
}

export async function loop(callback) {

    while (true) {
        await callback();
    }
}

// The WebSocket connection to the Admin console server
export const ws = new WebSocket(`ws://${window.location.hostname}:8765`)

ws.addEventListener("message", ev => {
    window.location.href = ev.data;
});

export const Results = Object.freeze({
    TARGET_SUCCESS: "TS",
    TARGET_FAILURE: "TF",
    NON_TARGET_SUCCESS: "NS",
    NON_TARGET_FAILURE: "NF"
});
