// Replay re/symbols.tsv onto the program: rename functions, (re)label data.
// TSV columns (tab-separated): 0xADDR <TAB> kind(func|data) <TAB> name
// Lines blank or starting with '#' are ignored. Creates a function/label if absent.
// Run headless (NOT -readOnly) so renames persist into the project.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;

public class ImportSymbols extends GhidraScript {
    public void run() throws Exception {
        File f = new File("/Users/jagi/Programming/h4/re/symbols.tsv");
        SymbolTable st = currentProgram.getSymbolTable();
        FunctionManager fm = currentProgram.getFunctionManager();
        int nf = 0, nd = 0, miss = 0;
        StringBuilder log = new StringBuilder();
        try (BufferedReader br = new BufferedReader(new FileReader(f))) {
            String line;
            while ((line = br.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty() || line.startsWith("#")) continue;
                String[] p = line.split("\\t+");
                if (p.length < 3) continue;
                long addr;
                try { addr = Long.decode(p[0].trim()); } catch (Exception e) { continue; }
                String kind = p[1].trim(), name = p[2].trim();
                Address a = toAddr(addr);
                try {
                    if (kind.equals("func")) {
                        Function fn = fm.getFunctionAt(a);
                        if (fn == null) fn = createFunction(a, name);
                        if (fn != null) { fn.setName(name, SourceType.USER_DEFINED); nf++; }
                        else { miss++; log.append("MISS func ").append(p[0]).append(' ').append(name).append('\n'); }
                    } else { // data / label
                        Symbol[] ex = st.getSymbols(a);
                        if (ex.length > 0) ex[0].setName(name, SourceType.USER_DEFINED);
                        else createLabel(a, name, true, SourceType.USER_DEFINED);
                        nd++;
                    }
                } catch (Exception e) {
                    miss++; log.append("ERR ").append(line).append(" : ").append(e.getMessage()).append('\n');
                }
            }
        }
        println("ImportSymbols: funcs=" + nf + " data=" + nd + " miss=" + miss);
        if (log.length() > 0) println(log.toString());
    }
}
