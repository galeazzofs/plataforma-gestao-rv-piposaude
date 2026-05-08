(ns app.ds.nav
  "Canonical sidebar navigation for the Pipo RV platform.
   Mirrors the grouping defined in the design handoff:
   visão geral / apuração / vendas / configuração.")

;; Each nav item is {:key :label :icon :route :badge?}.
;; Section markers are {:section \"label\"}.
;; Icon strings refer to <symbol id=\"i-...\"> defined in index.html.

(def admin-items
  [{:section "visão geral"}
   {:key :finance/dashboard      :label "Dashboard Financeiro" :icon "money"     :route :finance/dashboard}
   {:key :revops/dashboard       :label "Dashboard Admin"      :icon "dashboard" :route :revops/dashboard}
   {:key :lider-vendas/dashboard :label "Painel do Líder"      :icon "team"      :route :lider-vendas/dashboard}

   {:section "apuração"}
   {:key :revops/appraisal       :label "Apurações"            :icon "cog"     :route :revops/appraisal}
   {:key :revops/cn-appraisal    :label "Apuração CN"          :icon "percent" :route :revops/cn-appraisal}
   {:key :revops/cn-goals        :label "Metas CN"             :icon "target"  :route :revops/cn-goals}
   {:key :revops/ev-bonus            :label "Bônus EV"          :icon "money"   :route :revops/ev-bonus}
   {:key :revops/cn-quarterly-bonus  :label "Bônus CN trimestral" :icon "money" :route :revops/cn-quarterly-bonus}
   {:key :revops/leadership          :label "Liderança"         :icon "users"   :route :revops/leadership}
   {:key :revops/contestations   :label "Contestações"         :icon "alert"   :route :revops/contestations}

   {:section "vendas"}
   {:key :ev/dashboard           :label "EV · Dashboard"       :icon "trend"  :route :ev/dashboard}
   {:key :cn/simulator           :label "CN · Simulador"       :icon "target" :route :cn/simulator}

   {:section "configuração"}
   {:key :revops/policies         :label "Apólices"            :icon "doc"     :route :revops/policies}
   {:key :revops/users            :label "Usuários"            :icon "users"   :route :revops/users}
   {:key :revops/teams            :label "Times"               :icon "team"    :route :revops/teams}
   {:key :revops/achievements     :label "Atingimento EV"      :icon "trend"   :route :revops/achievements}
   {:key :revops/commission-table :label "Tabela %"            :icon "percent" :route :revops/commission-table}
   {:key :revops/financial        :label "Upload Financeiro"   :icon "upload"  :route :revops/financial}
   {:key :revops/sync-status      :label "Sync"                :icon "refresh" :route :revops/sync-status}
   {:key :revops/audit-log        :label "Audit Log"           :icon "list"    :route :revops/audit-log}])

(def ev-items
  [{:section "vendas"}
   {:key :ev/dashboard  :label "Dashboard"  :icon "trend"    :route :ev/dashboard}
   {:key :ev/history    :label "Histórico"  :icon "calendar" :route :ev/history}
   {:key :ev/validation :label "Validação"  :icon "check"    :route :ev/validation}
   {:key :cn/simulator  :label "Simulador"  :icon "target"   :route :cn/simulator}])

(def lider-vendas-items
  [{:section "gestão de time"}
   {:key :lider-vendas/dashboard :label "Painel do Líder" :icon "team"  :route :lider-vendas/dashboard}
   {:section "operação"}
   {:key :revops/appraisal     :label "Apurações"     :icon "cog"   :route :revops/appraisal}
   {:key :revops/contestations :label "Contestações"  :icon "alert" :route :revops/contestations}])

(def finance-items
  [{:section "visão geral"}
   {:key :finance/dashboard :label "Dashboard Financeiro" :icon "money" :route :finance/dashboard}
   {:key :finance/approval  :label "Aprovação"            :icon "check" :route :finance/approval}
   {:section "operação"}
   {:key :revops/policies   :label "Apólices"             :icon "doc"   :route :revops/policies}
   {:key :revops/audit-log  :label "Audit Log"            :icon "list"  :route :revops/audit-log}])

(defn items-for-role
  "Return the canonical sidebar nav for the given role."
  [role]
  (case role
    "ADMIN"   admin-items
    "REVOPS"  admin-items
    "FINANCE" finance-items
    "LIDER_VENDAS" lider-vendas-items
    "EV"      ev-items
    "CN"      ev-items
    admin-items))
