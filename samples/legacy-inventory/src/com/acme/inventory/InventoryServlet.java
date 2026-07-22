package com.acme.inventory;

import java.io.IOException;
import java.io.PrintWriter;
import java.sql.*;
import javax.servlet.http.*;

/**
 * Legacy inventory endpoint, circa 2009. Business logic, SQL, and HTML
 * are deliberately tangled together - this is the modernization target.
 */
public class InventoryServlet extends HttpServlet {

    private static final String DB_URL = "jdbc:mysql://prod-db:3306/acme";

    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        String sku = req.getParameter("sku");
        PrintWriter out = resp.getWriter();
        try (Connection c = DriverManager.getConnection(DB_URL, "app", "app")) {
            PreparedStatement ps = c.prepareStatement(
                "SELECT sku, name, qty, reorder_level, unit_price FROM inventory WHERE sku = ?");
            ps.setString(1, sku);
            ResultSet rs = ps.executeQuery();
            if (!rs.next()) { resp.setStatus(404); out.print("NOT FOUND"); return; }

            int qty = rs.getInt("qty");
            int reorder = rs.getInt("reorder_level");
            double price = rs.getDouble("unit_price");

            // BUSINESS RULE 1: items at/below reorder level are flagged, and
            // flagged items get a 0% discount regardless of quantity breaks.
            boolean needsReorder = qty <= reorder;

            // BUSINESS RULE 2: quantity price breaks - 5% off orders of 100+,
            // 12% off 500+, but never on items needing reorder.
            double discount = 0.0;
            if (!needsReorder) {
                int orderQty = Integer.parseInt(req.getParameter("orderQty") == null ? "0" : req.getParameter("orderQty"));
                if (orderQty >= 500) discount = 0.12;
                else if (orderQty >= 100) discount = 0.05;
            }

            // BUSINESS RULE 3: selling below qty 0 is impossible - clamp and log.
            if (qty < 0) { qty = 0; System.err.println("negative qty for " + sku); }

            out.print(rs.getString("sku") + "|" + rs.getString("name") + "|" + qty + "|"
                    + needsReorder + "|" + String.format("%.2f", price * (1 - discount)));
        } catch (SQLException e) {
            resp.setStatus(500);
            out.print("DB ERROR: " + e.getMessage());
        }
    }
}
