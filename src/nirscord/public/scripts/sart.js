import { ws, sleep, lock, Results, loop } from "./util.js";

/**
 * @type {HTMLHeadingElement}
 */
const sart = document.querySelector("#sart");

/**
 * @type {HTMLDivElement}
 */
const marker = document.querySelector("#marker");

let isSpace = true;
let isTarget = false;

function unique(target) {
    do {
        // Generate a random number between 1-9
        var digit = Math.ceil(Math.random() * 9);

    // Ensure tar gets are non-consecutive
    } while (isTarget && digit == target);

    // Set if digit is the target
    isTarget = digit == target;

    // Return the digit
    return digit;
}

document.addEventListener("keydown", lock(async ev => {
    if (ev.key !== " " || isSpace || ev.repeat) return;

    // Set the keypress
    isSpace = true;

    // Forward target results
    if (isTarget) {
        ws.send(Results.TARGET_FAILURE);

    } else {
        ws.send(Results.NON_TARGET_SUCCESS);
    }
}));

loop(async () => {
    let digit = unique('3');

    // Flash the digit on screen
    sart.innerHTML = digit;
    await sleep(500);
    sart.innerHTML = "X";
    await sleep(1000);

    // Forward non-target results
    if (!isSpace) {
        
        if (isTarget) {
            ws.send(Results.TARGET_SUCCESS);

        } else {
            ws.send(Results.NON_TARGET_FAILURE);
        }
    }

    // Reset the keypress
    isSpace = false;
});
