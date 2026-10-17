components {
  id: "mesh"
  component: "/main/platforms/burning/platform.mesh"
}
components {
  id: "mesh_default"
  component: "/main/platforms/default/platform.mesh"
}
components {
  id: "collision_object"
  component: "/main/platforms/platform.collisionobject"
}
components {
  id: "bend"
  component: "/main/platforms/platform.script"
}
components {
  id: "burning"
  component: "/main/platforms/burning/burning.script"
  properties {
    id: "burning"
    type: PROPERTY_TYPE_NUMBER
    value: "1"
  }
}
components {
  id: "slope"
  component: "/main/platforms/sloped/sloped.script"
  properties {
    id: "direction"
    type: PROPERTY_TYPE_NUMBER
    value: "0"
  }
}
