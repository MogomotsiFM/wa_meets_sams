const dns = require('dns').promises;
const net = require('net');

// Given an IP address, we determine the Autonomous System Organization name.
// This is a unique name/number assigned to organizations with large IP address alocations.
// Companies like ISPs, Facebook, Google, AWS, e.t.c

function expandIPv6(addr) {
    // Expand an IPv6 address to full 8 groups of 4 hex digits
    if (!addr.includes('::')) {
        return addr.split(':').map(s => s.padStart(4, '0')).join(':');
    }
    const parts = addr.split('::');
    const left = parts[0] ? parts[0].split(':').filter(Boolean) : [];
    const right = parts[1] ? parts[1].split(':').filter(Boolean) : [];
    const missing = 8 - (left.length + right.length);
    const zeros = new Array(missing).fill('0');
    const full = [...left, ...zeros, ...right].map(s => s.padStart(4, '0'));
    return full.join(':');
}

function ipv6ToCymruQuery(ipv6) {
    // Expand, remove colons, reverse nybbles and append origin6 domain
    const expanded = expandIPv6(ipv6);
    const hex = expanded.replace(/:/g, '');
    // split into chars, reverse, join with dots
    const nibbles = hex.split('');
    return `${nibbles.reverse().join('.')}.origin6.asn.cymru.com`;
}

function ipv4ToCymruQuery(ipv4) {
    return `${ipv4.split('.').reverse().join('.')}.origin.asn.cymru.com`;
}

async function queryCymru(query) {
    try {
        const records = await dns.resolveTxt(query);
        if (records && records.length > 0) {
            const record = records[0].join('');
            const parts = record.split(' | ').map(p => p.trim());
            return {
                asn: parts[0] || null,
                ip: parts[1] || null,
                country: parts[2] || null,
                rir: parts[3] || null,
                allocated: parts[4] || null,
                asoName: parts.slice(5).join(' | ') || null
            };
        }
    } catch (err) {
        // ignore per-address failures, caller can decide
    }
    return null;
}

async function getASO(ip_address) {
    const results = [];

    // If the input is already an IP address, skip DNS lookups and query directly.
    const ipVersion = net.isIP(ip_address);
    if (ipVersion === 4) {
        const q = ipv4ToCymruQuery(ip_address);
        const info = await queryCymru(q);
        if (info) info.ip = ip_address;
        return info || { ip, error: 'no-asn-record' };
    } else { // (ipVersion === 6) {
        const q = ipv6ToCymruQuery(ip_address);
        const info = await queryCymru(q);
        if (info) info.ip = ip_address;
        return info || { ip_address, error: 'no-asn-record' };
    }
}


process.stdin.on('data', (data) => {
    try {
        const input   = JSON.parse(data.toString());
        const address = input.address;

        (async () => {
            const asos = await getASO(address);
            console.log(JSON.stringify({asos: asos}));
        })();
    } catch (err) {
        console.error(JSON.stringify({'Error:': err.message}));
    }
});
