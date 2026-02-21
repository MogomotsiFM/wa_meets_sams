import MDBReader from 'mdb-reader';
import { readFileSync, writeFileSync } from 'fs';
import alasql from 'alasql';

import process from 'process';

function loadReader(dbPath) {
    const buffer = readFileSync(dbPath);
    return new MDBReader(buffer);
}

function registerTablesWithAlasql(reader, tableNames) {
    const aliasMap = {};
    tableNames.forEach((tblName, idx) => {
        const alias = `t${idx + 1}`; // t1, t2, t3...
        const table = reader.getTable(tblName);
        if (!table) throw new Error(`Table not found: ${tblName}`);
        const rows = table.getData();

        // Create a table in alasql and assign the rows as data
        alasql(`CREATE TABLE ${alias}`);
        // attach data array directly
        alasql.tables[alias].data = rows;

        aliasMap[tblName] = alias;
    });
    return aliasMap;
}

/**
 * Run an arbitrary SQL against registered aliases (t1, t2, t3...)
 * @param {string} sql - SQL string using aliases e.g. `SELECT * FROM t1 JOIN t2 ON t1.id = t2.t1_id JOIN t3 ON t2.id = t3.t2_id`
 * @returns {Array<Object>}
 */
function runSql(sql) {
    return alasql(sql);
}

// Example usage: register first three tables and run a 3-table JOIN.
process.stdin.on('data', (data) => {
    try {
        const input = JSON.parse(data.toString());
        const db_path = input.db_path;
        const reader = loadReader(db_path);

        const tables = reader.getTableNames();
        //console.log('Available tables:', tables);
        writeFileSync('all_tables.json', JSON.stringify(tables, null, 2));

        if (tables.length < 3) {
            //console.error('Database must contain at least 3 tables to demonstrate a 3-way join');
            return;
        }

        const [tblA, tblB, tblC] = ['Parent_Info', 'Parent_Child', 'Learner_Info'];

        // Register them as t1, t2, t3 in alasql
        const aliasMap = registerTablesWithAlasql(reader, [tblA, tblB, tblC]);

        const sampleSql = `
            SELECT t1.Tel1Code, t1.Tel1, t1.Tel2Code, t1.Tel2, t1.Tel3Code, t1.Tel3, t1.EMail, t1.IDNumber as ParentIDNo, t1.SpouseID, t3.SName, t3.FName, t3.SecondName, t3.IDNo as LearnerIDNo, t3.AccessionNo, t3.BirthDate
            FROM t1
            JOIN t2 ON t1.ParentId = t2.ParentID
            JOIN t3 ON t2.ChildId = t3.ID
        `;

        // Run the SQL
        const result = runSql(sampleSql);

        writeFileSync('join_result.json', JSON.stringify(result, null, 2));
        console.log(JSON.stringify({result: result}));
    } catch (err) {
        console.error(JSON.stringify({'Error:': err.message}));
    }
});